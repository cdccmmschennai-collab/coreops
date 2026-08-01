"""Biometric ingestion domain logic.

Everything Phase 2 does happens here: validate a connector batch, resolve
employee mappings, store raw punches idempotently, and finalize the sync-batch
record. Nothing in this module infers IN/OUT, pairs punches, or computes a
duration - punch-state semantics are unresolved and stay that way
(docs/attendance/punch-state-mapping.md).

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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.audit.constants import STATUS_FAILURE, AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.biometric.constants import (
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_ERRORS,
    BATCH_FAILED,
    BATCH_PROCESSING,
    ERROR_ALL_RECORDS_INVALID,
    ERROR_STORAGE_FAILURE,
    INVALID_DUPLICATE_IN_BATCH,
    INVALID_MISSING_EMPLOYEE_CODE,
    INVALID_MISSING_TRANSACTION_ID,
    INVALID_PUNCH_TIME,
    INVALID_PUNCH_TIME_OUT_OF_RANGE,
    MAX_PUNCH_AGE_DAYS,
    MAX_PUNCH_FUTURE_DAYS,
    MAX_RAW_PAYLOAD_CHARS,
    MAX_RAW_PAYLOAD_KEYS,
    MAX_RAW_PAYLOAD_VALUE_LEN,
    PII_KEYS,
    RAW_PUNCH_TIME_TEXT_KEY,
    RAW_UPLOAD_TIME_TEXT_KEY,
    SECRET_KEY_MARKERS,
    UNMAPPED_ALERT_MIN_RECORDS,
    UNMAPPED_ALERT_RATIO,
)
from app.modules.biometric.models import (
    BiometricEmployeeMapping,
    BiometricPunch,
    BiometricSyncBatch,
)
from app.modules.biometric.schemas import PunchBatchIn, PunchBatchResult, PunchIn
from app.modules.employees.models import Employee
from app.modules.users.models import User
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

def create_mapping(
    db: Session,
    *,
    actor: User,
    provider: str,
    external_employee_code: str,
    employee_id: uuid.UUID,
) -> BiometricEmployeeMapping:
    """Point an external code at a CoreOps employee.

    Idempotent when the active mapping already names the same employee.
    Re-pointing a code at a DIFFERENT employee deactivates the current row and
    inserts a new one, so the previous attribution stays visible in history;
    both paths are audited.

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

    current = db.execute(
        select(BiometricEmployeeMapping).where(
            BiometricEmployeeMapping.provider == provider,
            BiometricEmployeeMapping.external_employee_code == code,
            BiometricEmployeeMapping.is_active.is_(True),
        )
    ).scalar_one_or_none()

    if current is not None and current.employee_id == employee_id:
        return current

    now = _now()
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
        verified_at=now,
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
