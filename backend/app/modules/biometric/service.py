"""Biometric ingestion domain logic.

Everything Phase 2 does happens here: validate a connector batch, resolve
employee mappings, store raw punches idempotently, and finalize the sync-batch
record. Nothing on the INGESTION path infers IN/OUT, pairs punches, or computes a
duration - punch-state semantics are unresolved and stay that way
(docs/attendance/punch-state-mapping.md).

The read-only summary path (`list_daily_summary`) does compute an elapsed
duration and a conservative classification, both delegated to pure modules
(`summary.py`, `classification.py`) and neither stored: no punch, mapping or
attendance record is written by a read.

No EasyTime HTTP client lives here. The backend only ever sees the normalized
payload the office-side connector POSTs; talking to EasyTime is
`connectors/easytime`'s job and always will be.

Transaction boundaries are explicit and deliberate:

  T1  create-or-resolve the sync-batch row, COMMIT.
      The attempt is durable before any punch is touched, so a crash mid-write
      still leaves an operator-visible record instead of silence.
  T2  insert punches + write the counters + finalize status, COMMIT.
  T3  only on failure: reopen, mark the batch `failed` with a SANITIZED error,
      COMMIT, then re-raise.
"""
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Date, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.attendance.models import AttendanceRecord
from app.modules.audit.constants import STATUS_FAILURE, AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.biometric.classification import Shift, classify_day
from app.modules.biometric.constants import (
    BLOCKING_REVIEW_REASONS,
    CLASSIFICATIONS,
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_ERRORS,
    BATCH_FAILED,
    BATCH_PROCESSING,
    BULK_DUPLICATE_CODE_IN_REQUEST,
    BULK_DUPLICATE_EMPLOYEE_IN_REQUEST,
    BULK_EMPLOYEE_MAPPED_TO_OTHER_CODE,
    BULK_EMPLOYEE_NOT_FOUND,
    BULK_MAPPED,
    BULK_REMAP_NOT_ALLOWED,
    BULK_SKIPPED,
    BULK_UNCHANGED,
    CODE_STATUS_MAPPED,
    CODE_STATUS_UNMAPPED,
    ERROR_ALL_RECORDS_INVALID,
    ERROR_STORAGE_FAILURE,
    INVALID_DUPLICATE_IN_BATCH,
    INVALID_MISSING_EMPLOYEE_CODE,
    INVALID_MISSING_TRANSACTION_ID,
    INVALID_PUNCH_TIME,
    INVALID_PUNCH_TIME_OUT_OF_RANGE,
    MAX_PUNCH_AGE_DAYS,
    MAX_SUMMARY_RANGE_DAYS,
    MAX_PUNCH_FUTURE_DAYS,
    MAX_RAW_PAYLOAD_CHARS,
    MAX_RAW_PAYLOAD_KEYS,
    MAX_RAW_PAYLOAD_VALUE_LEN,
    PII_KEYS,
    RAW_PUNCH_TIME_TEXT_KEY,
    RAW_UPLOAD_TIME_TEXT_KEY,
    SECRET_KEY_MARKERS,
    SHIFT_SOURCE_OFFICE,
    UNMAPPED_ALERT_MIN_RECORDS,
    UNMAPPED_ALERT_RATIO,
)
from app.modules.biometric.models import (
    BiometricEmployeeMapping,
    BiometricPunch,
    BiometricSyncBatch,
)
from app.modules.biometric.schemas import (
    BulkMappingItem,
    PunchBatchIn,
    PunchBatchResult,
    PunchIn,
)
from app.modules.biometric.summary import EMPTY_DAY, summarize_day
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.offices.models import Office
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

logger = logging.getLogger("coreops.biometric.ingestion")

# Rows per INSERT statement. Well inside psycopg's 65535 bound-parameter limit
# (500 x ~16 columns) and keeps any single statement short-lived.
_INSERT_CHUNK = 500

# Accepted in addition to ISO 8601 (which datetime.fromisoformat already covers,
# including "2026-07-29 10:12:10" and a trailing "Z" on Python 3.11+).
_FALLBACK_TIMESTAMP_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _attendance_tz() -> ZoneInfo:
    """Zone used to interpret a NAIVE vendor timestamp.

    Deliberately raises on a misconfigured ATTENDANCE_TIMEZONE rather than
    falling back to UTC: silently reading naive Asia/Kolkata wall-clock values
    as UTC would shift every punch by 5h30m, which is exactly the kind of
    quiet, total corruption this integration is built to avoid.
    """
    return ZoneInfo(settings.ATTENDANCE_TIMEZONE)


# ── timestamps ──────────────────────────────────────────────────────────────

def parse_timestamp(value: str | None, *, tz: ZoneInfo) -> datetime | None:
    """Vendor timestamp text -> aware UTC datetime, or None if unusable.

    EasyTime returns naive local wall-clock values ("2026-07-29 10:12:10"). The
    connector normally attaches the +05:30 offset before POSTing; when it does
    not, the offset comes from `tz` here. Either way the value is converted to
    UTC for storage, matching every existing CoreOps timestamp column
    (TIMESTAMP WITH TIME ZONE). The ORIGINAL text is preserved in raw_payload
    under `_punch_time_text` / `_upload_time_text` so the exact string the device
    reported survives, and can be compared against the EasyTime UI later.
    """
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw:
        return None

    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        for fmt in _FALLBACK_TIMESTAMP_FORMATS:
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(timezone.utc)


# ── raw payload sanitization ────────────────────────────────────────────────

def sanitize_raw_payload(
    payload: dict | None,
    *,
    punch_time_text: str | None,
    upload_time_text: str | None,
) -> dict:
    """Reduce a vendor payload to storable scalars.

    Dropped outright, never stored:
      * PII keys (names, photo, face, fingerprint/vein/iris templates, contact
        details) - CoreOps needs a code and a timestamp, nothing else;
      * anything whose key looks secret-shaped (password / token / jwt /
        authorization / api_key / credential / cookie / session ...);
      * nested objects and arrays - the only place a base64 template or a
        credentials block realistically hides;
      * strings longer than MAX_RAW_PAYLOAD_VALUE_LEN. These are DROPPED rather
        than truncated: half a biometric template is still biometric material.

    Whatever survives is capped in key count and total serialized size, so a
    hostile or malfunctioning connector cannot use raw_payload as unbounded
    storage.
    """
    clean: dict = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if len(clean) >= MAX_RAW_PAYLOAD_KEYS:
                break
            if not isinstance(key, str):
                continue
            lowered = key.strip().lower()
            if not lowered or lowered in PII_KEYS:
                continue
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                continue
            if value is None or isinstance(value, (bool, int, float)):
                clean[key] = value
            elif isinstance(value, str):
                if len(value) <= MAX_RAW_PAYLOAD_VALUE_LEN:
                    clean[key] = value
            # dicts / lists / everything else: dropped.

    # Reserved keys always win, and are set last so a vendor field cannot
    # impersonate them.
    if punch_time_text:
        clean[RAW_PUNCH_TIME_TEXT_KEY] = punch_time_text[:MAX_RAW_PAYLOAD_VALUE_LEN]
    if upload_time_text:
        clean[RAW_UPLOAD_TIME_TEXT_KEY] = upload_time_text[:MAX_RAW_PAYLOAD_VALUE_LEN]

    # Final size guard: shed vendor keys (never the reserved ones) until the
    # serialized payload fits.
    while len(json.dumps(clean, default=str)) > MAX_RAW_PAYLOAD_CHARS:
        droppable = [
            k
            for k in clean
            if k not in (RAW_PUNCH_TIME_TEXT_KEY, RAW_UPLOAD_TIME_TEXT_KEY)
        ]
        if not droppable:
            break
        clean.pop(droppable[-1])
    return clean


# ── per-record preparation ──────────────────────────────────────────────────

@dataclass(frozen=True)
class _PreparedPunch:
    external_transaction_id: str
    external_employee_code: str
    punch_time: datetime
    upload_time: datetime | None
    raw_punch_state: str | None
    punch_state_display: str | None
    terminal_alias: str | None
    terminal_serial_number: str | None
    verification_type: str | None
    source: str | None
    raw_payload: dict


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _prepare(punch: PunchIn, *, tz: ZoneInfo, now: datetime) -> tuple[_PreparedPunch | None, str | None]:
    """Validate and normalize one punch. Returns (prepared, reason) - exactly
    one of the two is None.

    `raw_punch_state` is NOT validated against any vocabulary: the live probe
    returned "0" for every punch and null for every display label, so any value
    (including null) is accepted verbatim.
    """
    external_id = punch.external_transaction_id.strip()
    if not external_id:
        return None, INVALID_MISSING_TRANSACTION_ID

    code = punch.employee_code.strip()
    if not code:
        return None, INVALID_MISSING_EMPLOYEE_CODE

    punch_time = parse_timestamp(punch.punch_time, tz=tz)
    if punch_time is None:
        return None, INVALID_PUNCH_TIME
    if not (
        now - timedelta(days=MAX_PUNCH_AGE_DAYS)
        <= punch_time
        <= now + timedelta(days=MAX_PUNCH_FUTURE_DAYS)
    ):
        return None, INVALID_PUNCH_TIME_OUT_OF_RANGE

    # An unparseable upload_time is metadata noise, never a reason to reject a
    # real attendance event: the punch is stored with upload_time NULL.
    upload_time = parse_timestamp(punch.upload_time, tz=tz)

    return (
        _PreparedPunch(
            external_transaction_id=external_id,
            external_employee_code=code,
            punch_time=punch_time,
            upload_time=upload_time,
            raw_punch_state=_clean_optional(punch.raw_punch_state),
            punch_state_display=_clean_optional(punch.punch_state_display),
            terminal_alias=_clean_optional(punch.terminal_alias),
            terminal_serial_number=_clean_optional(punch.terminal_serial_number),
            verification_type=_clean_optional(punch.verify_type),
            source=_clean_optional(punch.source),
            raw_payload=sanitize_raw_payload(
                punch.raw_payload,
                punch_time_text=punch.punch_time,
                upload_time_text=punch.upload_time,
            ),
        ),
        None,
    )


# ── employee mapping ────────────────────────────────────────────────────────

def resolve_employee_ids(
    db: Session, *, provider: str, codes: set[str]
) -> dict[str, uuid.UUID]:
    """External employee codes -> CoreOps employee ids. Two queries, whatever
    the batch size.

    Resolution order, and nothing else is ever tried:

    1. An ACTIVE row in `biometric_employee_mappings` for
       (provider, external_employee_code). Explicit, human-verified, and always
       authoritative - it wins even when an exact code match also exists.
    2. Fallback: an EXACT, case-sensitive match on `employees.employee_code`
       among non-deleted employees. Deterministic because that column carries a
       partial unique index (`employees_code_uq` WHERE deleted_at IS NULL), so
       it resolves to at most one employee and can never guess. Disable with
       BIOMETRIC_EXACT_CODE_MATCH_ENABLED=false.

    Names are NEVER used for matching, in any form. The live probe returned bare
    numeric EasyTime codes ("61") while CoreOps uses prefixed codes ("EMP225"),
    so in practice step 2 rarely fires and step 1 is how punches get attributed.
    Anything unresolved returns absent from the dict; the caller stores the punch
    with employee_id = NULL rather than dropping it.
    """
    resolved: dict[str, uuid.UUID] = {}
    if not codes:
        return resolved

    rows = db.execute(
        select(
            BiometricEmployeeMapping.external_employee_code,
            BiometricEmployeeMapping.employee_id,
        ).where(
            BiometricEmployeeMapping.provider == provider,
            BiometricEmployeeMapping.external_employee_code.in_(codes),
            BiometricEmployeeMapping.is_active.is_(True),
        )
    ).all()
    for code, employee_id in rows:
        resolved[code] = employee_id

    remaining = codes - resolved.keys()
    if remaining and settings.BIOMETRIC_EXACT_CODE_MATCH_ENABLED:
        rows = db.execute(
            select(Employee.employee_code, Employee.id).where(
                Employee.employee_code.in_(remaining),
                Employee.deleted_at.is_(None),
            )
        ).all()
        for code, employee_id in rows:
            resolved[code] = employee_id

    return resolved


# ── sync batch lifecycle ────────────────────────────────────────────────────

def derive_batch_key(payload: PunchBatchIn) -> str:
    """Deterministic fallback batch key.

    `batch_key` is CONNECTOR-GENERATED by design: only the connector knows
    whether a POST is a retry of a previous attempt or a genuinely new window
    that happens to overlap. When it is omitted, the backend derives a stable
    key by hashing the batch identity and the sorted set of external transaction
    ids, so an identical retried payload still resolves the SAME sync-batch row.

    Punch-level idempotency does not depend on this at all - that is the
    UNIQUE(provider, external_transaction_id) constraint. The key only controls
    whether a retry reuses one batch record or opens a second one.
    """
    digest = hashlib.sha256()
    digest.update(payload.provider.encode())
    digest.update(b"\x00")
    digest.update(payload.connector_id.encode())
    digest.update(b"\x00")
    digest.update((payload.source_from_time or "").encode())
    digest.update(b"\x00")
    digest.update((payload.source_to_time or "").encode())
    for external_id in sorted(p.external_transaction_id for p in payload.punches):
        digest.update(b"\x00")
        digest.update(external_id.encode())
    return f"auto-{digest.hexdigest()}"


def _resolve_batch(
    db: Session, *, payload: PunchBatchIn, batch_key: str, tz: ZoneInfo
) -> BiometricSyncBatch:
    """Create the sync-batch row, or return the existing one for this key.

    Concurrency-safe: the INSERT ... ON CONFLICT DO NOTHING either wins or
    returns nothing, in which case the row another request just committed is
    selected. Never raises on a duplicate. Committed on its own so the attempt
    survives a later failure.
    """
    now = _now()
    # Core insert against the Table (not the mapped class): this is a plain
    # dialect INSERT, so the ORM never tries to interpret ON CONFLICT semantics.
    stmt = (
        pg_insert(BiometricSyncBatch.__table__)
        .values(
            provider=payload.provider,
            connector_id=payload.connector_id,
            batch_key=batch_key,
            source_from_time=parse_timestamp(payload.source_from_time, tz=tz),
            source_to_time=parse_timestamp(payload.source_to_time, tz=tz),
            started_at=now,
            status=BATCH_PROCESSING,
        )
        .on_conflict_do_nothing(constraint="biometric_sync_batches_key_uq")
        .returning(BiometricSyncBatch.__table__.c.id)
    )
    inserted_id = db.execute(stmt).scalar_one_or_none()
    db.commit()

    if inserted_id is not None:
        return db.get(BiometricSyncBatch, inserted_id)

    existing = db.execute(
        select(BiometricSyncBatch).where(
            BiometricSyncBatch.provider == payload.provider,
            BiometricSyncBatch.connector_id == payload.connector_id,
            BiometricSyncBatch.batch_key == batch_key,
        )
    ).scalar_one_or_none()
    if existing is None:  # pragma: no cover - only if the row vanished mid-flight
        raise AppError("conflict", "Could not resolve the sync batch.", 409)
    return existing


def _safe_error(exc: Exception) -> tuple[str, str]:
    """(error_code, error_message) that is safe to persist and to return.

    Only the exception CLASS NAME is used. Exception text routinely carries
    connection strings, SQL with bound parameters, and occasionally credentials;
    none of it belongs in a table an operator will read, so the detail stays in
    the server log and the row records the shape of the failure.
    """
    return (
        ERROR_STORAGE_FAILURE,
        f"Ingestion failed while storing punches ({type(exc).__name__}). "
        "See server logs for detail.",
    )


# ── ingestion ───────────────────────────────────────────────────────────────

def ingest_batch(db: Session, *, payload: PunchBatchIn) -> PunchBatchResult:
    """Store one connector batch idempotently and return deterministic counts.

    Counting contract:
        inserted + duplicates + invalid == received
        unmapped counts the newly INSERTED rows with employee_id IS NULL
        (a subset of `inserted`, not a fourth disjoint bucket).
    """
    tz = _attendance_tz()
    now = _now()
    received = len(payload.punches)
    batch_key = (payload.batch_key or "").strip() or derive_batch_key(payload)

    batch = _resolve_batch(db, payload=payload, batch_key=batch_key, tz=tz)

    try:
        counts = _store_punches(
            db, payload=payload, batch=batch, tz=tz, now=now, received=received
        )
    except Exception as exc:
        db.rollback()
        error_code, error_message = _safe_error(exc)
        _finalize(
            db,
            batch=batch,
            counts={
                "received": received,
                "inserted": 0,
                "duplicates": 0,
                "unmapped": 0,
                "invalid": 0,
            },
            status=BATCH_FAILED,
            error_code=error_code,
            error_message=error_message,
        )
        logger.exception(
            "biometric ingestion failed batch_id=%s connector_id=%s provider=%s "
            "received=%s status=%s",
            batch.id,
            payload.connector_id,
            payload.provider,
            received,
            BATCH_FAILED,
        )
        _audit_batch_failure(db, batch=batch, error_code=error_code)
        raise AppError(
            "ingestion_failed",
            "Could not store the punch batch. The attempt has been recorded; "
            "retry is safe.",
            500,
        ) from exc

    duration_ms = int((_now() - now).total_seconds() * 1000)
    logger.info(
        "biometric ingestion batch_id=%s connector_id=%s provider=%s "
        "received=%s inserted=%s duplicates=%s unmapped=%s invalid=%s "
        "duration_ms=%s status=%s",
        batch.id,
        payload.connector_id,
        payload.provider,
        counts["received"],
        counts["inserted"],
        counts["duplicates"],
        counts["unmapped"],
        counts["invalid"],
        duration_ms,
        counts["status"],
    )

    _maybe_audit_unmapped(db, batch=batch, counts=counts)

    return PunchBatchResult(
        batch_id=batch.id,
        received=counts["received"],
        inserted=counts["inserted"],
        duplicates=counts["duplicates"],
        unmapped=counts["unmapped"],
        invalid=counts["invalid"],
        status=counts["status"],
    )


def _store_punches(
    db: Session,
    *,
    payload: PunchBatchIn,
    batch: BiometricSyncBatch,
    tz: ZoneInfo,
    now: datetime,
    received: int,
) -> dict:
    """Validate, map and insert. Runs inside one transaction (T2)."""
    prepared: list[_PreparedPunch] = []
    invalid = 0
    reasons: dict[str, int] = {}
    seen: set[str] = set()

    for punch in payload.punches:
        record, reason = _prepare(punch, tz=tz, now=now)
        if record is None:
            invalid += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            continue
        # Two rows with the same vendor id inside ONE request: keep the first,
        # count the rest as duplicates. The DB constraint would also absorb
        # them, but counting here keeps the response honest about what happened.
        if record.external_transaction_id in seen:
            reasons[INVALID_DUPLICATE_IN_BATCH] = (
                reasons.get(INVALID_DUPLICATE_IN_BATCH, 0) + 1
            )
            continue
        seen.add(record.external_transaction_id)
        prepared.append(record)

    intra_batch_duplicates = reasons.get(INVALID_DUPLICATE_IN_BATCH, 0)

    mapping = resolve_employee_ids(
        db,
        provider=payload.provider,
        codes={r.external_employee_code for r in prepared},
    )

    inserted = 0
    unmapped = 0
    for start in range(0, len(prepared), _INSERT_CHUNK):
        chunk = prepared[start : start + _INSERT_CHUNK]
        rows = [
            {
                "provider": payload.provider,
                "external_transaction_id": r.external_transaction_id,
                "external_employee_code": r.external_employee_code,
                "employee_id": mapping.get(r.external_employee_code),
                "punch_time": r.punch_time,
                "upload_time": r.upload_time,
                "received_at": now,
                "raw_punch_state": r.raw_punch_state,
                "punch_state_display": r.punch_state_display,
                "terminal_alias": r.terminal_alias,
                "terminal_serial_number": r.terminal_serial_number,
                "verification_type": r.verification_type,
                "source": r.source,
                "sync_batch_id": batch.id,
                "raw_payload": r.raw_payload,
            }
            for r in chunk
        ]
        # THE idempotency mechanism. Duplicate protection is delegated to the
        # unique index, so two connectors replaying the same window concurrently
        # cannot both insert: the loser's rows are skipped, not rolled back, and
        # every genuinely new punch in the same statement still lands. A plain
        # INSERT would abort the whole statement on the first collision and take
        # the valid rows with it; a SELECT-then-INSERT pre-check would be a race.
        stmt = (
            pg_insert(BiometricPunch.__table__)
            .values(rows)
            .on_conflict_do_nothing(constraint="biometric_punches_provider_txn_uq")
            .returning(BiometricPunch.__table__.c.employee_id)
        )
        returned = db.execute(stmt).all()
        inserted += len(returned)
        unmapped += sum(1 for (employee_id,) in returned if employee_id is None)

    # Anything valid that did not insert was already stored by an earlier batch.
    duplicates = (len(prepared) - inserted) + intra_batch_duplicates

    if invalid == received and received > 0:
        status = BATCH_FAILED
        error_code = ERROR_ALL_RECORDS_INVALID
        error_message = "Every record in the batch was rejected by validation."
    elif invalid or unmapped:
        status = BATCH_COMPLETED_WITH_ERRORS
        error_code = None
        error_message = None
    else:
        status = BATCH_COMPLETED
        error_code = None
        error_message = None

    counts = {
        "received": received,
        "inserted": inserted,
        "duplicates": duplicates,
        "unmapped": unmapped,
        "invalid": invalid,
        "status": status,
        "reasons": reasons,
    }
    _finalize(
        db,
        batch=batch,
        counts=counts,
        status=status,
        error_code=error_code,
        error_message=error_message,
    )
    return counts


def _finalize(
    db: Session,
    *,
    batch: BiometricSyncBatch,
    counts: dict,
    status: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    """Write the counters and terminal status, then COMMIT.

    A re-POSTed batch key updates this row in place: the counters always
    describe the MOST RECENT attempt, and therefore always agree with the
    response the connector just received.
    """
    batch.records_received = counts["received"]
    batch.records_inserted = counts["inserted"]
    batch.records_duplicates = counts["duplicates"]
    batch.records_unmapped = counts["unmapped"]
    batch.records_invalid = counts["invalid"]
    batch.status = status
    batch.error_code = error_code
    batch.error_message = error_message
    batch.completed_at = _now()
    db.add(batch)
    db.commit()
    db.refresh(batch)


def _audit_batch_failure(
    db: Session, *, batch: BiometricSyncBatch, error_code: str
) -> None:
    record_audit(
        db,
        action=AuditAction.BIOMETRIC_BATCH_FAILED,
        actor=None,
        actor_role="connector",
        entity_type=EntityType.BIOMETRIC_SYNC_BATCH,
        entity_id=batch.id,
        status=STATUS_FAILURE,
        details={
            "provider": batch.provider,
            "connector_id": batch.connector_id,
            "error_code": error_code,
        },
        commit=True,
    )


def _maybe_audit_unmapped(
    db: Session, *, batch: BiometricSyncBatch, counts: dict
) -> None:
    """Flag a batch where most punches could not be attributed.

    Deliberately event-level: a successful batch of 500 punches writes ZERO
    audit rows. One row per punch would drown the audit log and make it useless
    for the security events it exists to record.
    """
    inserted = counts["inserted"]
    unmapped = counts["unmapped"]
    if inserted < UNMAPPED_ALERT_MIN_RECORDS:
        return
    if unmapped / inserted < UNMAPPED_ALERT_RATIO:
        return
    record_audit(
        db,
        action=AuditAction.BIOMETRIC_BATCH_UNMAPPED_HIGH,
        actor=None,
        actor_role="connector",
        entity_type=EntityType.BIOMETRIC_SYNC_BATCH,
        entity_id=batch.id,
        details={
            "provider": batch.provider,
            "connector_id": batch.connector_id,
            "inserted": inserted,
            "unmapped": unmapped,
        },
        commit=True,
    )


# ── administrative surfaces (project_manager only) ──────────────────────────

def _active_mapping(
    db: Session, *, provider: str, code: str
) -> BiometricEmployeeMapping | None:
    return db.execute(
        select(BiometricEmployeeMapping).where(
            BiometricEmployeeMapping.provider == provider,
            BiometricEmployeeMapping.external_employee_code == code,
            BiometricEmployeeMapping.is_active.is_(True),
        )
    ).scalar_one_or_none()


def _apply_mapping(
    db: Session,
    *,
    actor: User,
    provider: str,
    code: str,
    employee_id: uuid.UUID,
    current: BiometricEmployeeMapping | None,
) -> tuple[BiometricEmployeeMapping, bool]:
    """Write one mapping and its audit row. FLUSHES, never commits.

    Returns `(row, changed)`; `changed` is False when the active mapping already
    named this employee and nothing was written. Shared verbatim by the
    single-mapping endpoint and the bulk import, so both produce identical
    history and identical audit events - a bulk import is not a second, laxer
    code path.
    """
    if current is not None and current.employee_id == employee_id:
        return current, False

    previous_employee_id = None
    if current is not None:
        previous_employee_id = current.employee_id
        current.is_active = False
        db.add(current)
        # Release the partial unique index before the replacement is inserted.
        db.flush()

    row = BiometricEmployeeMapping(
        provider=provider,
        external_employee_code=code,
        employee_id=employee_id,
        is_active=True,
        verified_at=_now(),
        verified_by_user_id=actor.id,
    )
    db.add(row)
    db.flush()

    record_audit(
        db,
        action=(
            AuditAction.BIOMETRIC_MAPPING_CHANGED
            if previous_employee_id is not None
            else AuditAction.BIOMETRIC_MAPPING_CREATED
        ),
        actor=actor,
        entity_type=EntityType.BIOMETRIC_MAPPING,
        entity_id=row.id,
        details={
            "provider": provider,
            "external_employee_code": code,
            "employee_id": str(employee_id),
            **(
                {"previous_employee_id": str(previous_employee_id)}
                if previous_employee_id is not None
                else {}
            ),
        },
    )
    return row, True


def create_mapping(
    db: Session,
    *,
    actor: User,
    provider: str,
    external_employee_code: str,
    employee_id: uuid.UUID,
) -> BiometricEmployeeMapping:
    """Point an external code at a CoreOps employee.

    THE authoritative mapping-creation path. Idempotent when the active mapping
    already names the same employee. Re-pointing a code at a DIFFERENT employee
    deactivates the current row and inserts a new one, so the previous
    attribution stays visible in history; both paths are audited.

    Existing punches are NOT rewritten - raw punches are immutable. Attributing
    already-stored punches is a later phase's job, and it will read the mapping
    rather than mutate the punch.
    """
    employee = db.execute(
        select(Employee).where(
            Employee.id == employee_id, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none()
    if employee is None:
        raise AppError("validation_error", "Employee not found.", 422)

    code = external_employee_code.strip()
    if not code:
        raise AppError("validation_error", "External employee code is required.", 422)

    current = _active_mapping(db, provider=provider, code=code)
    row, changed = _apply_mapping(
        db,
        actor=actor,
        provider=provider,
        code=code,
        employee_id=employee_id,
        current=current,
    )
    if not changed:
        return row
    db.commit()
    db.refresh(row)
    return row


def deactivate_mapping(
    db: Session, *, actor: User, mapping_id: uuid.UUID
) -> BiometricEmployeeMapping:
    """Soft-deactivate a mapping. Idempotent; the row is never deleted, so the
    historical attribution stays auditable. Punches already stored keep their
    employee_id - they are immutable facts about what was known at the time."""
    row = db.get(BiometricEmployeeMapping, mapping_id)
    if row is None:
        raise AppError("not_found", "Mapping not found.", 404)
    if not row.is_active:
        return row

    row.is_active = False
    db.add(row)
    record_audit(
        db,
        action=AuditAction.BIOMETRIC_MAPPING_DEACTIVATED,
        actor=actor,
        entity_type=EntityType.BIOMETRIC_MAPPING,
        entity_id=row.id,
        details={
            "provider": row.provider,
            "external_employee_code": row.external_employee_code,
            "employee_id": str(row.employee_id),
        },
    )
    db.commit()
    db.refresh(row)
    return row


def list_mappings(
    db: Session,
    *,
    provider: str | None,
    is_active: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int]:
    stmt = select(BiometricEmployeeMapping)
    if provider:
        stmt = stmt.where(BiometricEmployeeMapping.provider == provider)
    if is_active is not None:
        stmt = stmt.where(BiometricEmployeeMapping.is_active.is_(is_active))

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    rows = db.execute(
        stmt.add_columns(
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
        )
        .join(Employee, BiometricEmployeeMapping.employee_id == Employee.id)
        .order_by(
            BiometricEmployeeMapping.provider,
            BiometricEmployeeMapping.external_employee_code,
            BiometricEmployeeMapping.created_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    ).all()

    items = []
    for mapping, employee_code, first_name, last_name in rows:
        items.append(
            {
                "id": mapping.id,
                "provider": mapping.provider,
                "external_employee_code": mapping.external_employee_code,
                "employee_id": mapping.employee_id,
                "employee_code": employee_code,
                "employee_name": f"{first_name} {last_name}".strip(),
                "is_active": mapping.is_active,
                "verified_at": mapping.verified_at,
                "verified_by_user_id": mapping.verified_by_user_id,
                "created_at": mapping.created_at,
                "updated_at": mapping.updated_at,
            }
        )
    return items, total


# ── Phase 5: the external-code operations view ──────────────────────────────

def list_external_codes(
    db: Session,
    *,
    provider: str,
    status: str | None,
    q: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict], int, dict]:
    """DISTINCT external employee codes seen in `biometric_punches`, with their
    mapping state.

    Nothing here proposes an employee. The PM reads the code and chooses, so no
    normalization rule, name comparison or similarity heuristic exists anywhere
    in this path - the only employee named in a response is one already stored in
    `biometric_employee_mappings`.

    Read-only in the strictest sense: it aggregates the raw punch table and
    LEFT JOINs the active mapping. No punch is read for mutation, and grouping
    by `external_employee_code` (not by `punch_time`) is what lets a code
    mapped TODAY still account for punches stored last month - the mapping
    table is the join, not a rewritten `employee_id` column.

    Returns `(page_items, filtered_total, summary)`.
    """
    # One row per distinct code: counts and the seen-window, straight from raw.
    agg = (
        select(
            BiometricPunch.external_employee_code.label("code"),
            func.count().label("punch_count"),
            func.min(BiometricPunch.punch_time).label("first_seen"),
            func.max(BiometricPunch.punch_time).label("last_seen"),
            # count(col) skips NULLs - this is "how many already carry an id".
            func.count(BiometricPunch.employee_id).label("attributed"),
        )
        .where(BiometricPunch.provider == provider)
        .group_by(BiometricPunch.external_employee_code)
        .subquery()
    )

    active_mapping_join = and_(
        BiometricEmployeeMapping.provider == provider,
        BiometricEmployeeMapping.external_employee_code == agg.c.code,
        BiometricEmployeeMapping.is_active.is_(True),
    )

    # Provider-wide totals, independent of the page and of any filter: the PM
    # needs "12 of 46 mapped" while looking at a filtered page 2.
    total_codes, mapped_codes = db.execute(
        select(func.count(), func.count(BiometricEmployeeMapping.id))
        .select_from(agg)
        .outerjoin(BiometricEmployeeMapping, active_mapping_join)
    ).one()

    stmt = (
        select(
            agg.c.code,
            agg.c.punch_count,
            agg.c.first_seen,
            agg.c.last_seen,
            agg.c.attributed,
            BiometricEmployeeMapping.id,
            BiometricEmployeeMapping.employee_id,
            BiometricEmployeeMapping.verified_at,
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
        )
        .select_from(agg)
        .outerjoin(BiometricEmployeeMapping, active_mapping_join)
        .outerjoin(Employee, Employee.id == BiometricEmployeeMapping.employee_id)
    )

    if status == CODE_STATUS_MAPPED:
        stmt = stmt.where(BiometricEmployeeMapping.id.isnot(None))
    elif status == CODE_STATUS_UNMAPPED:
        stmt = stmt.where(BiometricEmployeeMapping.id.is_(None))

    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                agg.c.code.ilike(like),
                Employee.employee_code.ilike(like),
                (Employee.first_name + " " + Employee.last_name).ilike(like),
            )
        )

    filtered_total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()

    # Numeric-ish ordering without a cast: lpad turns "59"/"091"/"1001" into
    # equal-width strings, so they sort 59, 91, 1001 instead of 091, 1001, 59.
    # A non-numeric code just sorts lexicographically, and no row can raise.
    rows = db.execute(
        stmt.order_by(func.lpad(agg.c.code, 20, "0")).limit(limit).offset(offset)
    ).all()

    # Codes ingestion would resolve by its own EXACT, case-sensitive fallback.
    # Deliberately the same predicate as _resolve_employee_ids step 2 (including
    # `exited` employees, which that path does not exclude) so the status shown
    # here cannot disagree with what ingestion actually does.
    exact_match_codes: set[str] = set()
    page_codes = {row[0] for row in rows}
    if settings.BIOMETRIC_EXACT_CODE_MATCH_ENABLED and page_codes:
        exact_match_codes = set(
            db.execute(
                select(Employee.employee_code).where(
                    Employee.employee_code.in_(page_codes),
                    Employee.deleted_at.is_(None),
                )
            ).scalars()
        )

    items: list[dict] = []
    for (
        code,
        punch_count,
        first_seen,
        last_seen,
        attributed,
        mapping_id,
        employee_id,
        verified_at,
        employee_code,
        first_name,
        last_name,
    ) in rows:
        items.append(
            {
                "provider": provider,
                "external_employee_code": code,
                "punch_count": punch_count,
                "first_seen": first_seen,
                "last_seen": last_seen,
                "status": (
                    CODE_STATUS_MAPPED if mapping_id is not None
                    else CODE_STATUS_UNMAPPED
                ),
                "mapping_id": mapping_id,
                "employee_id": employee_id,
                "employee_code": employee_code,
                "employee_name": (
                    f"{first_name} {last_name}".strip()
                    if first_name is not None
                    else None
                ),
                "verified_at": verified_at,
                "attributed_punch_count": attributed,
                # An exact code match is what ingestion itself would fall back
                # to, so a code with no mapping row is not necessarily orphaned.
                "resolves_by_exact_code": code in exact_match_codes,
            }
        )

    summary = {
        "total_codes": total_codes,
        "mapped_codes": mapped_codes,
        "unmapped_codes": total_codes - mapped_codes,
    }
    return items, filtered_total, summary


# ── Phase 6: daily biometric summary (read-only, shadow) ────────────────────

def _summary_scope(db: Session, actor: User) -> tuple[uuid.UUID | None, bool]:
    """(forced_employee_id, allowed) for a summary read.

    Mirrors attendance's `_apply_scope` so biometric observation is never more
    visible than the attendance it shadows: a project manager sees everyone,
    anyone else sees only their own employee record, and a user with no employee
    profile sees nothing.
    """
    if actor.role == UserRole.project_manager:
        return None, True
    me = _current_employee(db, actor)
    if me is None:
        return None, False
    return me.id, True


def _employee_shifts(
    db: Session, employee_ids: set[uuid.UUID]
) -> dict[uuid.UUID, Shift]:
    """Contracted shift per employee, for the Phase 7 comparison. One query.

    Read-only, and absent is normal rather than an error: `employees.office_id` is
    nullable, so an employee with no office is simply missing from the result and
    the caller falls back to `Shift.default`. Returning a partial dict rather than
    filling gaps here keeps "which employees have real configuration" visible to
    the caller instead of hiding it behind a default.
    """
    if not employee_ids:
        return {}
    rows = db.execute(
        select(
            Employee.id,
            Office.timezone,
            Office.shift_start,
            Office.shift_end,
            Office.break_minutes,
        )
        .select_from(Employee)
        .join(Office, Office.id == Employee.office_id)
        .where(Employee.id.in_(employee_ids))
    ).all()
    return {
        emp_id: Shift(
            start=shift_start,
            end=shift_end,
            timezone=tz,
            break_minutes=break_minutes,
            source=SHIFT_SOURCE_OFFICE,
        )
        for emp_id, tz, shift_start, shift_end, break_minutes in rows
    }


def _review_employees(db: Session, *, on_date: date) -> list[tuple]:
    """Everyone whose day should appear on the review for `on_date`. One query.

    Scope rules, all read-only and all deliberate:
      * soft-deleted employees are excluded outright;
      * `exited` employees are excluded - they are not expected to punch, and a
        permanent row of "No Record" for a leaver is noise, not review;
      * `on_leave` employees ARE included. A long-term leave status is exactly
        the context Phase 9 will supply; suppressing them here would hide a day
        rather than explain it;
      * anyone who had not joined yet on `on_date` is excluded, so a new hire
        does not retroactively appear as missing attendance for last month.
    """
    return db.execute(
        select(
            Employee.id,
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
        )
        .where(
            Employee.deleted_at.is_(None),
            Employee.status != EmployeeStatus.exited,
            or_(
                Employee.date_of_joining.is_(None),
                Employee.date_of_joining <= on_date,
            ),
        )
        .order_by(Employee.employee_code)
    ).all()


def _punches_for_day(
    db: Session, *, provider: str, on_date: date
) -> dict[uuid.UUID, list[datetime]]:
    """Punch instants for one attendance day, keyed by employee. One query.

    Attribution joins `biometric_employee_mappings`, never
    `biometric_punches.employee_id` - identical to `list_daily_summary`, and for
    the same reason: every punch in the real backfill was stored before any
    mapping existed, so reading the stored column would report an empty day
    forever.

    The day is bucketed in ATTENDANCE_TIMEZONE, so "14 August" means the IST date
    a person would name.
    """
    local_day = cast(
        func.timezone(settings.ATTENDANCE_TIMEZONE, BiometricPunch.punch_time), Date
    )
    rows = db.execute(
        select(Employee.id, BiometricPunch.punch_time)
        .select_from(BiometricPunch)
        .join(
            BiometricEmployeeMapping,
            and_(
                BiometricEmployeeMapping.provider == BiometricPunch.provider,
                BiometricEmployeeMapping.external_employee_code
                == BiometricPunch.external_employee_code,
                BiometricEmployeeMapping.is_active.is_(True),
            ),
        )
        .join(Employee, Employee.id == BiometricEmployeeMapping.employee_id)
        .where(
            BiometricPunch.provider == provider,
            Employee.deleted_at.is_(None),
            local_day == on_date,
        )
    ).all()

    grouped: dict[uuid.UUID, list[datetime]] = {}
    for employee_id, punch_time in rows:
        grouped.setdefault(employee_id, []).append(punch_time)
    return grouped


def _official_records(
    db: Session, *, on_date: date, employee_ids: set[uuid.UUID]
) -> dict[uuid.UUID, AttendanceRecord]:
    """The OFFICIAL attendance record for the day, where one exists. One query.

    Read-only from this module's point of view: biometric reports what the
    devices saw, `attendance_records` holds what a human decided, and the review
    screen shows both side by side. Nothing here writes that table - the PM does,
    through the attendance module's own endpoints, which own its validation and
    audit trail.
    """
    if not employee_ids:
        return {}
    rows = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.attendance_date == on_date,
            AttendanceRecord.employee_id.in_(employee_ids),
        )
    ).scalars()
    return {r.employee_id: r for r in rows}


def list_daily_review(
    db: Session,
    *,
    provider: str,
    on_date: date,
    classification: str | None,
    q: str | None = None,
    limit: int = 15,
    offset: int = 0,
) -> dict:
    """One attendance day across every in-scope employee, for PM review.

    THE DIFFERENCE FROM `list_daily_summary`, and why this is a separate read
    rather than a flag on that one: the summary is EVIDENCE-SHAPED - it returns
    the employee-days that have punches, over a date RANGE, scoped to the caller.
    Review is ROSTER-SHAPED: one date, every employee who was expected, including
    the ones with no punch at all. Those are different cardinalities (a month for
    one person vs one day for everyone) and different questions, and forcing both
    through one endpoint would have made the calendar's month query materialize
    an employee x day grid it never wanted.

    What is NOT duplicated: the boundary rule (`summarize_day`), the duration and
    verdict (`classify_day`), the shift lookup (`_employee_shifts`) and the day
    bucketing are the SAME code the summary uses. There is one calculation engine
    and this is a second caller of it, not a second copy.

    Read-only, absolutely: three SELECTs, no INSERT/UPDATE/DELETE, no
    `attendance_records` row, no punch touched, and NO synthetic punch invented
    for an employee who did not punch - a missing day is represented by an
    in-memory `EMPTY_DAY`, which is why it can never reach the database.

    Cost is three queries regardless of headcount: employees, the day's punches,
    and the office shifts. No per-employee query, no N+1.

    `counts` describes the WHOLE day and is computed before `classification`
    filters `items`, so a PM looking at "Needs review" still sees how many of the
    day's records that is out of.

    `q`, `limit` and `offset` filter and paginate `items` ONLY - exactly like
    `classification` already does. `counts` always describes the whole day
    before any of the three are applied, so the compact summary never lies
    about what the current page or search happens to show.
    """
    employees = _review_employees(db, on_date=on_date)
    employee_ids = {row[0] for row in employees}
    normalized_q = q.strip().lower() if q and q.strip() else None

    punches = _punches_for_day(db, provider=provider, on_date=on_date)
    shifts = _employee_shifts(db, employee_ids)
    official = _official_records(db, on_date=on_date, employee_ids=employee_ids)
    default_shift = Shift.default(timezone_name=settings.ATTENDANCE_TIMEZONE)

    items: list[dict] = []
    counts: dict[str, int] = {c: 0 for c in CLASSIFICATIONS}
    review_required_count = 0

    for employee_id, employee_code, first_name, last_name in employees:
        times = punches.get(employee_id)
        # No punches is an ABSENCE OF EVIDENCE, represented in memory only. It is
        # never an absence from work and never a stored row.
        day_summary = summarize_day(times) if times else EMPTY_DAY
        verdict = classify_day(
            day_summary,
            day=on_date,
            shift=shifts.get(employee_id) or default_shift,
        )

        counts[verdict.classification] = counts.get(verdict.classification, 0) + 1
        record = official.get(employee_id)

        # The official record is the SOURCE OF TRUTH for what a day means. Once a
        # human has ruled on a day it leaves the queue, even if the punches alone
        # could not settle it - that ruling is exactly the missing information.
        review_required = verdict.review_required and record is None
        if review_required:
            review_required_count += 1

        # Biometric evidence is immutable and complete evidence is not
        # improvable, so the PM may supply a time ONLY where the device did not
        # record one. Enforced in the UI from this flag rather than from the UI
        # re-deriving it, so both ends agree on what "missing" means.
        can_set_check_in = verdict.first_in is None
        can_set_check_out = verdict.last_out is None

        if classification is not None and verdict.classification != classification:
            continue

        if normalized_q:
            name = f"{first_name} {last_name}".strip().lower()
            code = (employee_code or "").lower()
            if normalized_q not in name and normalized_q not in code:
                continue

        items.append(
            {
                "employee_id": employee_id,
                "employee_code": employee_code,
                "employee_name": f"{first_name} {last_name}".strip(),
                "first_in": verdict.first_in,
                "last_out": verdict.last_out,
                "worked_minutes": verdict.worked_minutes,
                "scheduled_start_at": verdict.scheduled_start_at,
                "scheduled_end_at": verdict.scheduled_end_at,
                "scheduled_minutes": verdict.scheduled_minutes,
                "classification": verdict.classification,
                "review_required": review_required,
                "can_set_check_in": can_set_check_in,
                "can_set_check_out": can_set_check_out,
                "review_reasons": list(verdict.reasons),
                # The subset that actually demands attention. Split HERE because
                # BLOCKING_REVIEW_REASONS already lives here - a frontend copy of
                # that set would be a second policy that could drift.
                "blocking_reasons": [
                    r for r in verdict.reasons if r in BLOCKING_REVIEW_REASONS
                ],
                # The OFFICIAL record, when a human has already ruled on this day.
                # Read from `attendance_records` - biometric never writes it.
                "attendance_record_id": record.id if record else None,
                "attendance_status": record.status.value if record else None,
                "attendance_check_in_at": record.check_in_at if record else None,
                "attendance_check_out_at": record.check_out_at if record else None,
                "attendance_note": record.note if record else None,
            }
        )

    return {
        "review_date": on_date,
        "provider": provider,
        "items": items[offset : offset + limit],
        "total": len(items),
        "limit": limit,
        "offset": offset,
        "counts": {
            **counts,
            "employees": len(employees),
            "review_required": review_required_count,
        },
    }


def _employee_schedule(db: Session, employee_id: uuid.UUID) -> dict | None:
    """The employee's office hours: CoreOps' own contracted data, not biometric.

    Read-only, and absent is normal - `employees.office_id` is nullable, so an
    employee with no office simply has no scheduled window to compare against.
    """
    row = db.execute(
        select(
            Office.name,
            Office.timezone,
            Office.shift_start,
            Office.shift_end,
            Office.break_minutes,
        )
        .select_from(Employee)
        .join(Office, Office.id == Employee.office_id)
        .where(Employee.id == employee_id, Employee.deleted_at.is_(None))
    ).one_or_none()
    if row is None:
        return None
    name, tz, shift_start, shift_end, break_minutes = row
    return {
        "office_name": name,
        "timezone": tz,
        "shift_start": shift_start,
        "shift_end": shift_end,
        "break_minutes": break_minutes,
    }


def list_daily_summary(
    db: Session,
    *,
    actor: User,
    provider: str,
    employee_id: uuid.UUID | None,
    date_from: date,
    date_to: date,
) -> tuple[list[dict], dict | None]:
    """First IN / last OUT per mapped employee per attendance day, plus Phase 7's
    worked duration and conservative classification.

    Read-only in the strictest sense: it SELECTs punches and writes nothing. The
    duration and the verdict are computed per request and stored nowhere - no
    `attendance_records` row is created or touched, and no punch is rewritten.
    The result is observation that a caller may display beside the official
    record, which remains authoritative.

    Only days that HAVE punches produce a row. A day with no biometric record is
    absent from `items` rather than being reported as absent from work: the reason
    could be leave, a holiday, or a device that failed to record, and deciding
    which is not this layer's job.

    Attribution goes through `biometric_employee_mappings`, never through
    `biometric_punches.employee_id`. That matters on real data: every punch in
    the production backfill was stored with `employee_id = NULL` because it
    arrived before any mapping existed, so reading the stored column would report
    an empty calendar forever. Joining the mapping table is what makes a mapping
    created today apply to punches stored last month, with no punch rewritten.

    Days are bucketed in ATTENDANCE_TIMEZONE, so a 01:00 IST punch belongs to the
    IST date a person would name, not to the UTC date.

    Returns `(items, schedule)`. `schedule` is the office window for the single
    employee in scope, or None - it is CoreOps data included so a reviewer can
    compare a derived boundary against contracted hours without a second request,
    including on a day that has no punches at all.
    """
    forced_employee_id, allowed = _summary_scope(db, actor)
    if not allowed:
        return [], None
    if forced_employee_id is not None and employee_id not in (None, forced_employee_id):
        # Asking for somebody else's summary is not a silent empty page.
        raise AppError("forbidden", "You can only view your own biometric summary.", 403)
    if forced_employee_id is not None:
        employee_id = forced_employee_id

    if date_to < date_from:
        raise AppError("validation_error", "'to' must not be before 'from'.", 422)
    span_days = (date_to - date_from).days + 1
    if span_days > MAX_SUMMARY_RANGE_DAYS:
        raise AppError(
            "validation_error",
            f"Date range must not exceed {MAX_SUMMARY_RANGE_DAYS} days.",
            422,
        )

    # The punch's attendance day, in local terms. `timezone(zone, timestamptz)`
    # yields the naive local wall clock, which cast to date is the IST day.
    local_day = cast(
        func.timezone(settings.ATTENDANCE_TIMEZONE, BiometricPunch.punch_time), Date
    ).label("summary_date")

    stmt = (
        select(
            Employee.id,
            Employee.employee_code,
            Employee.first_name,
            Employee.last_name,
            local_day,
            BiometricPunch.punch_time,
            BiometricPunch.external_employee_code,
        )
        .select_from(BiometricPunch)
        .join(
            BiometricEmployeeMapping,
            and_(
                BiometricEmployeeMapping.provider == BiometricPunch.provider,
                BiometricEmployeeMapping.external_employee_code
                == BiometricPunch.external_employee_code,
                BiometricEmployeeMapping.is_active.is_(True),
            ),
        )
        .join(Employee, Employee.id == BiometricEmployeeMapping.employee_id)
        .where(
            BiometricPunch.provider == provider,
            Employee.deleted_at.is_(None),
            local_day >= date_from,
            local_day <= date_to,
        )
        .order_by(Employee.employee_code, local_day, BiometricPunch.punch_time)
    )
    if employee_id is not None:
        stmt = stmt.where(Employee.id == employee_id)

    # Group in Python so the boundary rule lives in one pure, tested place
    # (summary.py) rather than being restated in SQL.
    grouped: dict[tuple[uuid.UUID, date], dict] = {}
    for emp_id, emp_code, first_name, last_name, day, punch_time, ext_code in db.execute(
        stmt
    ):
        bucket = grouped.setdefault(
            (emp_id, day),
            {
                "employee_id": emp_id,
                "employee_code": emp_code,
                "employee_name": f"{first_name} {last_name}".strip(),
                "summary_date": day,
                "_times": [],
                "_codes": set(),
            },
        )
        bucket["_times"].append(punch_time)
        bucket["_codes"].add(ext_code)

    # Phase 7 needs each employee's contracted window. Resolved once for the whole
    # page rather than per row: a month of days for one employee is one query, not
    # thirty.
    shifts = _employee_shifts(db, {emp_id for emp_id, _day in grouped})

    items: list[dict] = []
    for bucket in grouped.values():
        day_summary = summarize_day(bucket.pop("_times"))
        codes = bucket.pop("_codes")
        # Phase 7: duration and a conservative verdict, computed here and stored
        # nowhere. An employee with no office falls back to the module default,
        # and the row says so via `shift_source`.
        verdict = classify_day(
            day_summary,
            day=bucket["summary_date"],
            shift=shifts.get(bucket["employee_id"])
            or Shift.default(timezone_name=settings.ATTENDANCE_TIMEZONE),
        )
        items.append(
            {
                **bucket,
                "first_in": day_summary.first_in,
                "last_out": day_summary.last_out,
                "punch_count": day_summary.punch_count,
                "kept_count": day_summary.kept_count,
                # The punches the boundary was taken from, for human review.
                "punch_times": list(day_summary.kept),
                # More than one code here means two device codes map to the same
                # employee - worth seeing rather than silently merging.
                "external_employee_codes": sorted(codes),
                "worked_minutes": verdict.worked_minutes,
                "scheduled_start_at": verdict.scheduled_start_at,
                "scheduled_end_at": verdict.scheduled_end_at,
                "scheduled_minutes": verdict.scheduled_minutes,
                "shift_source": verdict.shift_source,
                "classification": verdict.classification,
                "review_required": verdict.review_required,
                "review_reasons": list(verdict.reasons),
            }
        )

    items.sort(key=lambda i: (i["summary_date"], i["employee_code"] or ""))
    schedule = _employee_schedule(db, employee_id) if employee_id is not None else None
    return items, schedule


# ── Phase 5: reviewed bulk import ───────────────────────────────────────────

def create_mappings_bulk(
    db: Session,
    *,
    actor: User,
    provider: str,
    items: list[BulkMappingItem],
    allow_remap: bool,
) -> dict:
    """Apply a list of PM-confirmed pairings in one transaction.

    Every pair comes from the caller. The server derives NO pair of its own here
    - if it did, "bulk import" would quietly become "the machine decided", which
    is the exact failure this module exists to prevent.

    Nothing ambiguous is ever written. A code listed twice, an employee listed
    twice, an employee already mapped under a different code, or a code that
    would be re-pointed without `allow_remap` are all SKIPPED with a reason and
    leave the database untouched. Each write goes through `_apply_mapping`, so
    history and audit rows are identical to the one-at-a-time endpoint.

    Raw punches are not touched. Mapping a code today makes its OLD punches
    attributable through this table; it does not rewrite them.
    """
    normalized: list[tuple[str, uuid.UUID]] = []
    for item in items:
        code = item.external_employee_code.strip()
        if not code:
            raise AppError(
                "validation_error", "External employee code is required.", 422
            )
        normalized.append((code, item.employee_id))

    # Ambiguity inside the request itself, detected before anything is written.
    code_counts: dict[str, int] = {}
    employee_counts: dict[uuid.UUID, int] = {}
    for code, employee_id in normalized:
        code_counts[code] = code_counts.get(code, 0) + 1
        employee_counts[employee_id] = employee_counts.get(employee_id, 0) + 1

    valid_employee_ids = set(
        db.execute(
            select(Employee.id).where(
                Employee.id.in_({e for _, e in normalized}),
                Employee.deleted_at.is_(None),
            )
        ).scalars()
    )

    existing = {
        row.external_employee_code: row
        for row in db.execute(
            select(BiometricEmployeeMapping).where(
                BiometricEmployeeMapping.provider == provider,
                BiometricEmployeeMapping.external_employee_code.in_(
                    {c for c, _ in normalized}
                ),
                BiometricEmployeeMapping.is_active.is_(True),
            )
        ).scalars()
    }

    # Employee -> the code they are ALREADY actively mapped under, provider-wide.
    employee_to_code = {
        employee_id: code
        for employee_id, code in db.execute(
            select(
                BiometricEmployeeMapping.employee_id,
                BiometricEmployeeMapping.external_employee_code,
            ).where(
                BiometricEmployeeMapping.provider == provider,
                BiometricEmployeeMapping.is_active.is_(True),
            )
        ).all()
    }

    results: list[dict] = []
    counts = {BULK_MAPPED: 0, BULK_UNCHANGED: 0, BULK_SKIPPED: 0}

    def _skip(code: str, employee_id: uuid.UUID, reason: str) -> None:
        counts[BULK_SKIPPED] += 1
        results.append(
            {
                "external_employee_code": code,
                "status": BULK_SKIPPED,
                "reason": reason,
                "employee_id": employee_id,
                "mapping_id": None,
            }
        )

    for code, employee_id in normalized:
        if code_counts[code] > 1:
            _skip(code, employee_id, BULK_DUPLICATE_CODE_IN_REQUEST)
            continue
        if employee_counts[employee_id] > 1:
            _skip(code, employee_id, BULK_DUPLICATE_EMPLOYEE_IN_REQUEST)
            continue
        if employee_id not in valid_employee_ids:
            _skip(code, employee_id, BULK_EMPLOYEE_NOT_FOUND)
            continue

        current = existing.get(code)
        if current is not None and current.employee_id == employee_id:
            counts[BULK_UNCHANGED] += 1
            results.append(
                {
                    "external_employee_code": code,
                    "status": BULK_UNCHANGED,
                    "reason": None,
                    "employee_id": employee_id,
                    "mapping_id": current.id,
                }
            )
            continue

        held = employee_to_code.get(employee_id)
        if held is not None and held != code:
            # This employee is already the target of another external code.
            # Legitimate in principle (two devices), but never something a bulk
            # import should decide on its own.
            _skip(code, employee_id, BULK_EMPLOYEE_MAPPED_TO_OTHER_CODE)
            continue

        if current is not None and not allow_remap:
            _skip(code, employee_id, BULK_REMAP_NOT_ALLOWED)
            continue

        row, _changed = _apply_mapping(
            db,
            actor=actor,
            provider=provider,
            code=code,
            employee_id=employee_id,
            current=current,
        )
        employee_to_code[employee_id] = code
        counts[BULK_MAPPED] += 1
        results.append(
            {
                "external_employee_code": code,
                "status": BULK_MAPPED,
                "reason": None,
                "employee_id": employee_id,
                "mapping_id": row.id,
            }
        )

    db.commit()

    logger.info(
        "biometric bulk mapping provider=%s actor=%s requested=%s mapped=%s "
        "unchanged=%s skipped=%s allow_remap=%s",
        provider,
        actor.id,
        len(normalized),
        counts[BULK_MAPPED],
        counts[BULK_UNCHANGED],
        counts[BULK_SKIPPED],
        allow_remap,
    )

    return {
        "provider": provider,
        "requested": len(normalized),
        "mapped": counts[BULK_MAPPED],
        "unchanged": counts[BULK_UNCHANGED],
        "skipped": counts[BULK_SKIPPED],
        "items": results,
    }


def list_sync_batches(
    db: Session,
    *,
    provider: str | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[BiometricSyncBatch], int]:
    stmt = select(BiometricSyncBatch)
    if provider:
        stmt = stmt.where(BiometricSyncBatch.provider == provider)
    if status:
        stmt = stmt.where(BiometricSyncBatch.status == status)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(BiometricSyncBatch.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total
