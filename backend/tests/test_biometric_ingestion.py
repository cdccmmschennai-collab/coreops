"""EasyTime raw-punch ingestion (Phase 2, migration 0063).

Covers connector authentication, per-record validation, idempotent insertion,
sync-batch bookkeeping, employee mapping, and the guarantee that ingestion
leaves the existing attendance system completely alone.

Every test here is database-backed: punches are asserted as real rows through
the `db` fixture, not as return values from a mocked function.
"""
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select

from app.modules.attendance.models import AttendanceRecord
from app.modules.audit.constants import AuditAction
from app.modules.audit.models import AuditLog
from app.modules.biometric.constants import (
    BATCH_COMPLETED,
    BATCH_COMPLETED_WITH_ERRORS,
    BATCH_FAILED,
    CONNECTOR_TOKEN_HEADER,
    ERROR_ALL_RECORDS_INVALID,
    MAX_BATCH_SIZE,
    RAW_PUNCH_TIME_TEXT_KEY,
)
from app.modules.biometric.models import (
    BiometricEmployeeMapping,
    BiometricPunch,
    BiometricSyncBatch,
)
from app.modules.users.models import UserRole

INGEST = "/api/v1/integrations/easytime/punches/batch"
MAPPINGS = "/api/v1/biometric/mappings"
BATCHES = "/api/v1/biometric/sync-batches"

TOKEN = "connector-token-that-is-long-enough-abcdef0123456789"
WRONG_TOKEN = "connector-token-that-is-long-enough-abcdef0123456788"


# ── fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture()
def ingestion_on():
    """Enable ingestion with a configured token for the duration of one test.
    The autouse `_default_feature_flags` fixture restores both afterwards."""
    from app.core.config import settings

    settings.EASYTIME_INGESTION_ENABLED = True
    settings.EASYTIME_CONNECTOR_TOKEN = TOKEN
    return settings


@pytest.fixture()
def conn_headers():
    return {CONNECTOR_TOKEN_HEADER: TOKEN}


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def ingestion_logs():
    """Capture the ingestion logger directly.

    A handler attached to the logger itself, rather than pytest's `caplog`,
    which depends on propagation and root-level configuration and would make an
    "the token never appears in a log" assertion pass vacuously if it captured
    nothing.

    `disabled` must be cleared explicitly. The session-scoped `_prepare_database`
    fixture runs Alembic IN-PROCESS, and `alembic/env.py` calls
    `logging.config.fileConfig(...)`, which defaults to
    disable_existing_loggers=True and therefore switches off every logger
    created before it - including this one. That is a test-harness artifact
    only: in production Alembic runs from entrypoint.sh as a separate process,
    so the API process never sees it.
    """
    logger = logging.getLogger("coreops.biometric.ingestion")
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collect(level=logging.DEBUG)
    previous_level = logger.level
    previous_disabled = logger.disabled
    logger.disabled = False
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = previous_disabled


def _punch(txn_id, code="61", punch_time="2026-07-29T10:12:10+05:30", **over):
    """One punch in the connector's normalized shape.

    Defaults mirror the live Phase 1 probe exactly: numeric EasyTime code,
    raw state "0", null display label.
    """
    body = {
        "external_transaction_id": str(txn_id),
        "employee_code": code,
        "punch_time": punch_time,
        "raw_punch_state": "0",
        "punch_state_display": None,
        "terminal_alias": "F22/ID",
        "terminal_serial_number": "CDC-DEV-01",
        "verify_type": "1",
        "source": "1",
        "upload_time": "2026-07-29T10:12:14+05:30",
    }
    body.update(over)
    return body


def _batch(punches, *, batch_key="batch-1", connector_id="admin-pc-01", **over):
    body = {
        "provider": "easytime",
        "connector_id": connector_id,
        "batch_key": batch_key,
        "source_from_time": "2026-07-29T00:00:00+05:30",
        "source_to_time": "2026-07-29T23:59:59+05:30",
        "punches": punches,
    }
    body.update(over)
    return body


def _post(client, headers, punches, **kw):
    return client.post(INGEST, json=_batch(punches, **kw), headers=headers)


def _punch_count(db):
    return db.execute(select(func.count()).select_from(BiometricPunch)).scalar_one()


# ── authentication ──────────────────────────────────────────────────────────

def test_ingestion_disabled_returns_404(client, conn_headers):
    """Off by default: the route must not even admit it exists."""
    res = _post(client, conn_headers, [_punch(1)])
    assert res.status_code == 404, res.text
    assert res.json()["error"]["code"] == "not_found"


def test_disabled_ingestion_stores_nothing(client, conn_headers, db):
    _post(client, conn_headers, [_punch(1)])
    assert _punch_count(db) == 0
    assert db.execute(
        select(func.count()).select_from(BiometricSyncBatch)
    ).scalar_one() == 0


def test_missing_token_unauthorized(client, ingestion_on):
    res = _post(client, {}, [_punch(1)])
    assert res.status_code == 401, res.text
    assert res.json()["error"]["code"] == "unauthorized"


def test_wrong_token_unauthorized(client, ingestion_on):
    res = _post(client, {CONNECTOR_TOKEN_HEADER: WRONG_TOKEN}, [_punch(1)])
    assert res.status_code == 401, res.text


def test_user_jwt_is_not_accepted_as_connector_auth(client, ingestion_on, pm):
    """A project-manager JWT must not open the machine endpoint."""
    res = _post(client, pm, [_punch(1)])
    assert res.status_code == 401, res.text


def test_token_in_query_string_is_not_accepted(client, ingestion_on):
    res = client.post(
        f"{INGEST}?token={TOKEN}", json=_batch([_punch(1)]), headers={}
    )
    assert res.status_code == 401, res.text


def test_empty_configured_token_rejects_everything(client):
    """Enabled but tokenless (only reachable in local/test - Settings refuses to
    boot in this state elsewhere): nothing authenticates, not even an empty
    header."""
    from app.core.config import settings

    settings.EASYTIME_INGESTION_ENABLED = True
    settings.EASYTIME_CONNECTOR_TOKEN = ""
    assert _post(client, {CONNECTOR_TOKEN_HEADER: ""}, [_punch(1)]).status_code == 401
    assert _post(client, {}, [_punch(1)]).status_code == 401


def test_correct_token_accepted(client, ingestion_on, conn_headers):
    res = _post(client, conn_headers, [_punch(1)])
    assert res.status_code == 200, res.text
    assert res.json()["inserted"] == 1


def test_token_never_appears_in_response_or_audit(
    client, ingestion_on, conn_headers, db, ingestion_logs
):
    """The supplied secret must not leak into a body, an audit row or a log."""
    ok = _post(client, conn_headers, [_punch(1)])
    bad = _post(client, {CONNECTOR_TOKEN_HEADER: WRONG_TOKEN}, [_punch(2)])

    assert TOKEN not in ok.text
    assert WRONG_TOKEN not in bad.text

    # The logger really did emit (otherwise the two checks below are vacuous).
    assert ingestion_logs
    logged = "\n".join(r.getMessage() for r in ingestion_logs)
    assert TOKEN not in logged
    assert WRONG_TOKEN not in logged

    rows = db.execute(select(AuditLog)).scalars().all()
    for row in rows:
        blob = f"{row.action}{row.details}{row.actor_email}"
        assert TOKEN not in blob
        assert WRONG_TOKEN not in blob


def test_auth_failure_is_audited_without_token_material(
    client, ingestion_on, conn_headers, db
):
    _post(client, {CONNECTOR_TOKEN_HEADER: WRONG_TOKEN}, [_punch(1)])
    row = db.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.BIOMETRIC_CONNECTOR_AUTH_FAILED
        )
    ).scalar_one()
    assert row.status == "failure"
    assert row.details["reason"] == "invalid"
    assert WRONG_TOKEN not in str(row.details)


# ── validation ──────────────────────────────────────────────────────────────

def test_empty_batch_rejected(client, ingestion_on, conn_headers):
    res = _post(client, conn_headers, [])
    assert res.status_code == 422, res.text


def test_missing_external_transaction_id_field_rejected(
    client, ingestion_on, conn_headers
):
    punch = _punch(1)
    del punch["external_transaction_id"]
    assert _post(client, conn_headers, [punch]).status_code == 422


def test_blank_external_transaction_id_counted_invalid(
    client, ingestion_on, conn_headers, db
):
    """One unusable row costs one `invalid`; the good rows still land."""
    res = _post(
        client, conn_headers, [_punch("", code="61"), _punch(2), _punch(3)]
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["invalid"] == 1
    assert body["inserted"] == 2
    assert _punch_count(db) == 2


def test_missing_employee_code_field_rejected(client, ingestion_on, conn_headers):
    punch = _punch(1)
    del punch["employee_code"]
    assert _post(client, conn_headers, [punch]).status_code == 422


def test_blank_employee_code_counted_invalid(client, ingestion_on, conn_headers, db):
    res = _post(client, conn_headers, [_punch(1, code="   "), _punch(2)])
    assert res.json()["invalid"] == 1
    assert res.json()["inserted"] == 1
    assert _punch_count(db) == 1


def test_invalid_timestamp_counted_invalid(client, ingestion_on, conn_headers, db):
    res = _post(
        client, conn_headers, [_punch(1, punch_time="not-a-timestamp"), _punch(2)]
    )
    assert res.status_code == 200, res.text
    assert res.json()["invalid"] == 1
    assert res.json()["inserted"] == 1
    assert _punch_count(db) == 1


def test_out_of_range_timestamp_counted_invalid(client, ingestion_on, conn_headers):
    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    res = _post(client, conn_headers, [_punch(1, punch_time=far_future)])
    assert res.json()["invalid"] == 1
    assert res.json()["status"] == BATCH_FAILED


def test_unsupported_provider_rejected(client, ingestion_on, conn_headers):
    res = client.post(
        INGEST, json=_batch([_punch(1)], provider="acme-biometrics"), headers=conn_headers
    )
    assert res.status_code == 422, res.text


def test_excessive_batch_size_rejected(client, ingestion_on, conn_headers):
    punches = [_punch(i) for i in range(MAX_BATCH_SIZE + 1)]
    assert _post(client, conn_headers, punches).status_code == 422


def test_max_batch_size_accepted(client, ingestion_on, conn_headers, db):
    punches = [_punch(i) for i in range(MAX_BATCH_SIZE)]
    res = _post(client, conn_headers, punches)
    assert res.status_code == 200, res.text
    assert res.json()["inserted"] == MAX_BATCH_SIZE
    assert _punch_count(db) == MAX_BATCH_SIZE


def test_null_raw_state_accepted(client, ingestion_on, conn_headers, db):
    """`raw_punch_state` is not validated against any vocabulary - null is fine."""
    res = _post(
        client,
        conn_headers,
        [_punch(1, raw_punch_state=None, punch_state_display=None)],
    )
    assert res.status_code == 200, res.text
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.raw_punch_state is None
    assert row.punch_state_display is None


def test_oversized_field_rejected(client, ingestion_on, conn_headers):
    res = _post(client, conn_headers, [_punch("x" * 500)])
    assert res.status_code == 422, res.text


def test_connector_id_required(client, ingestion_on, conn_headers):
    res = client.post(
        INGEST, json=_batch([_punch(1)], connector_id=""), headers=conn_headers
    )
    assert res.status_code == 422, res.text


# ── insertion & idempotency ─────────────────────────────────────────────────

def test_new_punches_inserted_with_raw_fields_preserved(
    client, ingestion_on, conn_headers, db
):
    res = _post(client, conn_headers, [_punch(10432)])
    assert res.status_code == 200, res.text

    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.provider == "easytime"
    assert row.external_transaction_id == "10432"
    assert row.external_employee_code == "61"
    assert row.raw_punch_state == "0"
    assert row.punch_state_display is None
    assert row.terminal_alias == "F22/ID"
    assert row.terminal_serial_number == "CDC-DEV-01"
    assert row.verification_type == "1"
    assert row.source == "1"
    assert row.received_at is not None
    assert row.sync_batch_id is not None


def test_raw_state_zero_is_stored_verbatim(client, ingestion_on, conn_headers, db):
    """No IN/OUT inference anywhere: "0" in, "0" out."""
    _post(client, conn_headers, [_punch(i, raw_punch_state="0") for i in range(1, 5)])
    states = set(db.execute(select(BiometricPunch.raw_punch_state)).scalars())
    assert states == {"0"}


def test_repeat_identical_batch_inserts_no_duplicate_rows(
    client, ingestion_on, conn_headers, db
):
    punches = [_punch(1), _punch(2), _punch(3)]
    first = _post(client, conn_headers, punches).json()
    assert first["inserted"] == 3 and first["duplicates"] == 0

    second = _post(client, conn_headers, punches).json()
    assert second["inserted"] == 0
    assert second["duplicates"] == 3
    assert second["received"] == 3
    assert _punch_count(db) == 3


def test_repeat_with_new_punches_inserts_only_the_new_ones(
    client, ingestion_on, conn_headers, db
):
    """The overlap window the connector re-fetches every run: old punches are
    absorbed, new ones still land in the same request."""
    _post(client, conn_headers, [_punch(1), _punch(2)], batch_key="b1")
    res = _post(
        client, conn_headers, [_punch(1), _punch(2), _punch(3), _punch(4)], batch_key="b2"
    ).json()
    assert res["inserted"] == 2
    assert res["duplicates"] == 2
    assert _punch_count(db) == 4


def test_duplicate_ids_within_one_request(client, ingestion_on, conn_headers, db):
    res = _post(client, conn_headers, [_punch(7), _punch(7), _punch(7), _punch(8)]).json()
    assert res["received"] == 4
    assert res["inserted"] == 2
    assert res["duplicates"] == 2
    assert res["invalid"] == 0
    assert _punch_count(db) == 2


def test_count_invariant_holds(client, ingestion_on, conn_headers):
    """inserted + duplicates + invalid == received, always."""
    res = _post(
        client,
        conn_headers,
        [_punch(1), _punch(1), _punch(2), _punch("", code="61"), _punch(3)],
    ).json()
    assert res["inserted"] + res["duplicates"] + res["invalid"] == res["received"]


def test_concurrent_identical_batches_insert_each_punch_once(
    client, ingestion_on, conn_headers, db
):
    """Duplicate protection is the DB unique index, so racing connectors cannot
    both insert. Total inserted across both responses must equal the punch
    count, and no punch may be stored twice."""
    punches = [_punch(i) for i in range(1, 21)]

    def _run(key):
        return client.post(
            INGEST, json=_batch(punches, batch_key=key), headers=conn_headers
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_run, ["race-a", "race-b"]))

    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert sum(r.json()["inserted"] for r in results) == 20
    assert sum(r.json()["duplicates"] for r in results) == 20
    assert _punch_count(db) == 20


def test_intermediate_punches_stay_separate_rows(client, ingestion_on, conn_headers, db):
    """The live probe returned four punches for employee 61 on one day. All four
    are kept as distinct rows - nothing is collapsed to a first/last pair."""
    times = [
        "2026-07-29T10:12:10+05:30",
        "2026-07-29T13:05:44+05:30",
        "2026-07-29T13:28:31+05:30",
        "2026-07-29T17:48:54+05:30",
    ]
    res = _post(
        client,
        conn_headers,
        [_punch(i, code="61", punch_time=t) for i, t in enumerate(times, start=100)],
    ).json()
    assert res["inserted"] == 4

    rows = db.execute(
        select(BiometricPunch)
        .where(BiometricPunch.external_employee_code == "61")
        .order_by(BiometricPunch.punch_time)
    ).scalars().all()
    assert len(rows) == 4
    assert [r.punch_time.astimezone(timezone.utc).strftime("%H:%M:%S") for r in rows] == [
        "04:42:10",
        "07:35:44",
        "07:58:31",
        "12:18:54",
    ]


def test_late_upload_time_does_not_replace_punch_time(
    client, ingestion_on, conn_headers, db
):
    """Some punches are uploaded the following morning. `upload_time` records
    the arrival; `punch_time` stays the attendance event."""
    _post(
        client,
        conn_headers,
        [
            _punch(
                1,
                punch_time="2026-07-29T17:48:54+05:30",
                upload_time="2026-07-30T09:02:11+05:30",
            )
        ],
    )
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.punch_time.astimezone(timezone.utc).date() == date(2026, 7, 29)
    assert row.upload_time.astimezone(timezone.utc).date() == date(2026, 7, 30)
    assert row.punch_time < row.upload_time


def test_unparseable_upload_time_does_not_reject_the_punch(
    client, ingestion_on, conn_headers, db
):
    res = _post(client, conn_headers, [_punch(1, upload_time="garbage")]).json()
    assert res["inserted"] == 1
    assert res["invalid"] == 0
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.upload_time is None


def test_multiple_pages_accumulate(client, ingestion_on, conn_headers, db):
    for page in range(3):
        res = _post(
            client,
            conn_headers,
            [_punch(page * 10 + i) for i in range(10)],
            batch_key=f"page-{page}",
        )
        assert res.json()["inserted"] == 10
    assert _punch_count(db) == 30
    assert db.execute(
        select(func.count()).select_from(BiometricSyncBatch)
    ).scalar_one() == 3


# ── timezone handling ───────────────────────────────────────────────────────

def test_offset_timestamp_is_converted_to_utc(client, ingestion_on, conn_headers, db):
    _post(client, conn_headers, [_punch(1, punch_time="2026-07-29T10:12:10+05:30")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.punch_time.astimezone(timezone.utc) == datetime(
        2026, 7, 29, 4, 42, 10, tzinfo=timezone.utc
    )


def test_naive_timestamp_is_read_as_asia_kolkata(client, ingestion_on, conn_headers, db):
    """EasyTime's own format, with no offset attached by the connector."""
    _post(client, conn_headers, [_punch(1, punch_time="2026-07-29 10:12:10")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.punch_time.astimezone(timezone.utc) == datetime(
        2026, 7, 29, 4, 42, 10, tzinfo=timezone.utc
    )


def test_original_timestamp_text_is_preserved_in_raw_payload(
    client, ingestion_on, conn_headers, db
):
    _post(client, conn_headers, [_punch(1, punch_time="2026-07-29 10:12:10")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.raw_payload[RAW_PUNCH_TIME_TEXT_KEY] == "2026-07-29 10:12:10"


# ── raw payload sanitization ────────────────────────────────────────────────

def test_raw_payload_strips_pii_and_secrets(client, ingestion_on, conn_headers, db):
    _post(
        client,
        conn_headers,
        [
            _punch(
                1,
                raw_payload={
                    "emp_code": "61",
                    "first_name": "Ravi",
                    "last_name": "Kumar",
                    "photo": "data:image/png;base64,AAAA",
                    "face_template": "QUJDRA==",
                    "fingerprint": "0102030405",
                    "password": "hunter2",
                    "access_token": "eyJhbGciOi",
                    "authorization": "JWT abc",
                    "nested": {"secret": "x"},
                    "listy": [1, 2, 3],
                    "checktype": "0",
                },
            )
        ],
    )
    row = db.execute(select(BiometricPunch)).scalar_one()
    payload = row.raw_payload

    for banned in (
        "first_name",
        "last_name",
        "photo",
        "face_template",
        "fingerprint",
        "password",
        "access_token",
        "authorization",
        "nested",
        "listy",
    ):
        assert banned not in payload, banned
    assert payload["emp_code"] == "61"
    assert payload["checktype"] == "0"
    assert "hunter2" not in str(payload)
    assert "eyJhbGciOi" not in str(payload)


def test_raw_payload_drops_oversized_values(client, ingestion_on, conn_headers, db):
    _post(client, conn_headers, [_punch(1, raw_payload={"blob": "A" * 5000})])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert "blob" not in row.raw_payload


# ── employee mapping ────────────────────────────────────────────────────────

def test_unmapped_punches_are_retained_with_null_employee(
    client, ingestion_on, conn_headers, db
):
    """An unknown EasyTime code must never cost a punch."""
    res = _post(client, conn_headers, [_punch(1, code="9999")]).json()
    assert res["inserted"] == 1
    assert res["unmapped"] == 1
    assert res["status"] == BATCH_COMPLETED_WITH_ERRORS

    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id is None
    assert row.external_employee_code == "9999"


def test_explicit_mapping_resolves_employee_id(
    client, ingestion_on, conn_headers, db, pm, make_employee
):
    emp = make_employee(employee_code="EMP225")
    created = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )
    assert created.status_code == 201, created.text

    res = _post(client, conn_headers, [_punch(1, code="61")]).json()
    assert res["inserted"] == 1
    assert res["unmapped"] == 0
    assert res["status"] == BATCH_COMPLETED

    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id == emp.id
    # The device's own code is still retained alongside the resolution.
    assert row.external_employee_code == "61"


def test_exact_employee_code_match_resolves(
    client, ingestion_on, conn_headers, db, make_employee
):
    """Deterministic fallback: employees.employee_code is uniquely indexed."""
    emp = make_employee(employee_code="EMP225")
    _post(client, conn_headers, [_punch(1, code="EMP225")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id == emp.id


def test_exact_match_can_be_disabled(client, ingestion_on, conn_headers, db, make_employee):
    from app.core.config import settings

    make_employee(employee_code="EMP225")
    settings.BIOMETRIC_EXACT_CODE_MATCH_ENABLED = False
    _post(client, conn_headers, [_punch(1, code="EMP225")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id is None


def test_explicit_mapping_wins_over_exact_match(
    client, ingestion_on, conn_headers, db, pm, make_employee
):
    exact = make_employee(employee_code="EMP225")
    intended = make_employee(employee_code="EMP226")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "EMP225",
            "employee_id": str(intended.id),
        },
        headers=pm,
    )
    _post(client, conn_headers, [_punch(1, code="EMP225")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id == intended.id
    assert row.employee_id != exact.id


def test_names_are_never_used_for_matching(
    client, ingestion_on, conn_headers, db, make_employee
):
    make_employee(employee_code="EMP300", first_name="Ravi", last_name="Kumar")
    _post(client, conn_headers, [_punch(1, code="Ravi Kumar")])
    row = db.execute(select(BiometricPunch)).scalar_one()
    assert row.employee_id is None


def test_mapping_created_is_audited(client, pm, db, make_employee):
    emp = make_employee(employee_code="EMP225")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )
    row = db.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.BIOMETRIC_MAPPING_CREATED
        )
    ).scalar_one()
    assert row.details["external_employee_code"] == "61"
    assert row.details["employee_id"] == str(emp.id)


def test_remapping_deactivates_the_previous_row_and_audits_the_change(
    client, pm, db, make_employee
):
    first = make_employee(employee_code="EMP225")
    second = make_employee(employee_code="EMP226")
    body = {"provider": "easytime", "external_employee_code": "61"}

    client.post(MAPPINGS, json={**body, "employee_id": str(first.id)}, headers=pm)
    res = client.post(
        MAPPINGS, json={**body, "employee_id": str(second.id)}, headers=pm
    )
    assert res.status_code == 201, res.text

    rows = db.execute(
        select(BiometricEmployeeMapping).order_by(
            BiometricEmployeeMapping.created_at
        )
    ).scalars().all()
    assert len(rows) == 2
    assert [r.is_active for r in rows] == [False, True]
    assert rows[1].employee_id == second.id

    changed = db.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.BIOMETRIC_MAPPING_CHANGED
        )
    ).scalar_one()
    assert changed.details["previous_employee_id"] == str(first.id)


def test_remapping_to_the_same_employee_is_idempotent(client, pm, db, make_employee):
    emp = make_employee(employee_code="EMP225")
    body = {
        "provider": "easytime",
        "external_employee_code": "61",
        "employee_id": str(emp.id),
    }
    client.post(MAPPINGS, json=body, headers=pm)
    client.post(MAPPINGS, json=body, headers=pm)
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 1


def test_one_external_code_cannot_map_to_two_active_employees(
    client, pm, db, make_employee
):
    a = make_employee(employee_code="EMP225")
    b = make_employee(employee_code="EMP226")
    body = {"provider": "easytime", "external_employee_code": "61"}
    client.post(MAPPINGS, json={**body, "employee_id": str(a.id)}, headers=pm)
    client.post(MAPPINGS, json={**body, "employee_id": str(b.id)}, headers=pm)

    active = db.execute(
        select(BiometricEmployeeMapping).where(
            BiometricEmployeeMapping.external_employee_code == "61",
            BiometricEmployeeMapping.is_active.is_(True),
        )
    ).scalars().all()
    assert len(active) == 1


def test_mapping_unknown_employee_rejected(client, pm):
    res = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(uuid.uuid4()),
        },
        headers=pm,
    )
    assert res.status_code == 422, res.text


def test_mapping_endpoints_are_pm_only(client, auth_header, make_employee):
    emp = make_employee(employee_code="EMP225")
    emp_header = auth_header("emp@x.com", role=UserRole.employee)
    res = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=emp_header,
    )
    assert res.status_code == 403, res.text
    assert client.get(MAPPINGS, headers=emp_header).status_code == 403


def test_mapping_list_requires_auth(client):
    assert client.get(MAPPINGS).status_code == 401


def test_deactivated_mapping_stops_resolving(
    client, ingestion_on, conn_headers, db, pm, make_employee
):
    emp = make_employee(employee_code="EMP225")
    created = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    ).json()

    _post(client, conn_headers, [_punch(1, code="61")], batch_key="b1")
    client.delete(f"{MAPPINGS}/{created['id']}", headers=pm)
    _post(client, conn_headers, [_punch(2, code="61")], batch_key="b2")

    rows = db.execute(
        select(BiometricPunch).order_by(BiometricPunch.external_transaction_id)
    ).scalars().all()
    # The earlier punch keeps the attribution it was stored with - punches are
    # immutable - while the later one is unmapped.
    assert rows[0].employee_id == emp.id
    assert rows[1].employee_id is None


# ── sync batches ────────────────────────────────────────────────────────────

def test_completed_batch_statistics(client, ingestion_on, conn_headers, db, make_employee):
    make_employee(employee_code="EMP225")
    res = _post(
        client, conn_headers, [_punch(1, code="EMP225"), _punch(2, code="EMP225")]
    ).json()
    assert res["status"] == BATCH_COMPLETED

    batch = db.execute(select(BiometricSyncBatch)).scalar_one()
    assert batch.records_received == 2
    assert batch.records_inserted == 2
    assert batch.records_duplicates == 0
    assert batch.records_unmapped == 0
    assert batch.records_invalid == 0
    assert batch.status == BATCH_COMPLETED
    assert batch.completed_at is not None
    assert batch.error_code is None and batch.error_message is None
    assert batch.batch_key == "batch-1"
    assert batch.connector_id == "admin-pc-01"
    assert batch.source_from_time is not None and batch.source_to_time is not None
    assert str(batch.id) == res["batch_id"]


def test_completed_with_errors_statistics(client, ingestion_on, conn_headers, db):
    res = _post(
        client,
        conn_headers,
        [_punch(1, code="9999"), _punch(2, punch_time="nope")],
    ).json()
    assert res["status"] == BATCH_COMPLETED_WITH_ERRORS

    batch = db.execute(select(BiometricSyncBatch)).scalar_one()
    assert batch.records_received == 2
    assert batch.records_inserted == 1
    assert batch.records_unmapped == 1
    assert batch.records_invalid == 1
    assert batch.status == BATCH_COMPLETED_WITH_ERRORS


def test_all_invalid_batch_is_failed_with_sanitized_error(
    client, ingestion_on, conn_headers, db
):
    res = _post(
        client, conn_headers, [_punch(1, punch_time="x"), _punch(2, punch_time="y")]
    ).json()
    assert res["status"] == BATCH_FAILED
    assert res["invalid"] == 2
    assert res["inserted"] == 0

    batch = db.execute(select(BiometricSyncBatch)).scalar_one()
    assert batch.status == BATCH_FAILED
    assert batch.error_code == ERROR_ALL_RECORDS_INVALID
    assert batch.error_message
    for leak in (TOKEN, "postgresql", "password"):
        assert leak not in batch.error_message


def test_repeat_batch_key_reuses_one_batch_row(client, ingestion_on, conn_headers, db):
    punches = [_punch(1), _punch(2)]
    first = _post(client, conn_headers, punches, batch_key="same").json()
    second = _post(client, conn_headers, punches, batch_key="same").json()

    assert first["batch_id"] == second["batch_id"]
    assert db.execute(
        select(func.count()).select_from(BiometricSyncBatch)
    ).scalar_one() == 1

    batch = db.execute(select(BiometricSyncBatch)).scalar_one()
    # The row always describes the MOST RECENT attempt, so it agrees with the
    # response the connector just received.
    assert batch.records_inserted == second["inserted"] == 0
    assert batch.records_duplicates == second["duplicates"] == 2
    assert batch.status == second["status"]


def test_derived_batch_key_when_omitted(client, ingestion_on, conn_headers, db):
    body = _batch([_punch(1), _punch(2)])
    del body["batch_key"]
    first = client.post(INGEST, json=body, headers=conn_headers).json()
    second = client.post(INGEST, json=body, headers=conn_headers).json()

    assert first["batch_id"] == second["batch_id"]
    batch = db.execute(select(BiometricSyncBatch)).scalar_one()
    assert batch.batch_key.startswith("auto-")


def test_batch_status_is_always_finalized(client, ingestion_on, conn_headers, db):
    _post(client, conn_headers, [_punch(1)], batch_key="a")
    _post(client, conn_headers, [_punch(2, punch_time="bad")], batch_key="b")
    statuses = set(db.execute(select(BiometricSyncBatch.status)).scalars())
    assert "processing" not in statuses


def test_sync_batches_endpoint_lists_attempts(
    client, ingestion_on, conn_headers, pm, make_employee
):
    make_employee(employee_code="EMP225")
    # "a" is fully mapped -> completed; "b" is unmapped -> completed_with_errors.
    _post(client, conn_headers, [_punch(1, code="EMP225")], batch_key="a")
    _post(client, conn_headers, [_punch(2, code="9999")], batch_key="b")

    res = client.get(BATCHES, headers=pm)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["total"] == 2
    assert {i["batch_key"] for i in body["items"]} == {"a", "b"}

    filtered = client.get(
        BATCHES, params={"status": BATCH_COMPLETED_WITH_ERRORS}, headers=pm
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["batch_key"] == "b"


def test_sync_batches_endpoint_is_pm_only(client, auth_header):
    emp_header = auth_header("emp@x.com", role=UserRole.employee)
    assert client.get(BATCHES, headers=emp_header).status_code == 403
    assert client.get(BATCHES).status_code == 401


def test_sync_batches_bad_status_filter_rejected(client, pm):
    assert client.get(BATCHES, params={"status": "nope"}, headers=pm).status_code == 422


# ── structured observability ────────────────────────────────────────────────

def test_ingestion_logs_the_batch_summary(
    client, ingestion_on, conn_headers, ingestion_logs
):
    res = _post(client, conn_headers, [_punch(1), _punch(1), _punch(2, code="9999")])
    assert res.status_code == 200, res.text
    assert ingestion_logs, "the ingestion logger emitted nothing"
    line = ingestion_logs[0].getMessage()
    for field in (
        "batch_id=",
        "connector_id=",
        "provider=",
        "received=",
        "inserted=",
        "duplicates=",
        "unmapped=",
        "invalid=",
        "duration_ms=",
        "status=",
    ):
        assert field in line, field


def test_successful_punches_do_not_flood_the_audit_log(
    client, ingestion_on, conn_headers, db, make_employee
):
    """Event-level auditing: 20 mapped punches must write ZERO audit rows."""
    make_employee(employee_code="EMP225")
    res = _post(
        client, conn_headers, [_punch(i, code="EMP225") for i in range(20)]
    ).json()
    assert res["inserted"] == 20
    assert db.execute(select(func.count()).select_from(AuditLog)).scalar_one() == 0


def test_high_unmapped_ratio_is_audited(client, ingestion_on, conn_headers, db):
    _post(client, conn_headers, [_punch(i, code="9999") for i in range(10)])
    row = db.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.BIOMETRIC_BATCH_UNMAPPED_HIGH
        )
    ).scalar_one()
    assert row.details["unmapped"] == 10


# ── configuration fail-closed ───────────────────────────────────────────────

def _settings(**over):
    from app.core.config import Settings

    base = {
        "ENV": "production",
        "SECRET_KEY": "s" * 48,
        # Do not let a developer's backend/.env leak into these assertions.
        "_env_file": None,
    }
    base.update(over)
    return Settings(**base)


def test_production_refuses_to_boot_with_ingestion_on_and_no_token():
    with pytest.raises(ValidationError):
        _settings(EASYTIME_INGESTION_ENABLED=True, EASYTIME_CONNECTOR_TOKEN="")


def test_production_refuses_a_short_connector_token():
    with pytest.raises(ValidationError):
        _settings(EASYTIME_INGESTION_ENABLED=True, EASYTIME_CONNECTOR_TOKEN="short")


def test_production_accepts_a_strong_connector_token():
    cfg = _settings(EASYTIME_INGESTION_ENABLED=True, EASYTIME_CONNECTOR_TOKEN="k" * 48)
    assert cfg.EASYTIME_INGESTION_ENABLED is True


def test_production_tokenless_is_fine_while_ingestion_is_off():
    """The guard fires only when the feature is actually enabled."""
    cfg = _settings(EASYTIME_INGESTION_ENABLED=False, EASYTIME_CONNECTOR_TOKEN="")
    assert cfg.EASYTIME_INGESTION_ENABLED is False


def test_local_env_may_run_tokenless_for_development():
    cfg = _settings(
        ENV="local", EASYTIME_INGESTION_ENABLED=True, EASYTIME_CONNECTOR_TOKEN=""
    )
    assert cfg.ENV == "local"


def test_ingestion_defaults_to_off():
    cfg = _settings(ENV="local")
    assert cfg.EASYTIME_INGESTION_ENABLED is False
    assert cfg.EASYTIME_CONNECTOR_TOKEN == ""
    assert cfg.ATTENDANCE_TIMEZONE == "Asia/Kolkata"


# ── existing behaviour is untouched ─────────────────────────────────────────

def test_ingestion_creates_no_attendance_row(
    client, ingestion_on, conn_headers, db, make_employee
):
    """The single most important guarantee of Phase 2: punches go in, and the
    official attendance system does not move."""
    make_employee(employee_code="EMP225")
    before = db.execute(select(func.count()).select_from(AttendanceRecord)).scalar_one()
    _post(client, conn_headers, [_punch(i, code="EMP225") for i in range(5)])
    after = db.execute(select(func.count()).select_from(AttendanceRecord)).scalar_one()
    assert before == after == 0


def test_ingestion_does_not_modify_an_existing_attendance_row(
    client, ingestion_on, conn_headers, db, make_employee, make_attendance
):
    emp = make_employee(employee_code="EMP225")
    record = make_attendance(
        employee_id=emp.id, attendance_date=date(2026, 7, 29), total_minutes=480
    )
    original = (record.status, record.total_minutes, record.check_in_at, record.updated_at)

    _post(
        client,
        conn_headers,
        [_punch(i, code="EMP225", punch_time="2026-07-29T10:12:10+05:30") for i in range(4)],
    )
    db.expire_all()
    fresh = db.get(AttendanceRecord, record.id)
    assert (fresh.status, fresh.total_minutes, fresh.check_in_at, fresh.updated_at) == original


def test_no_session_or_duration_is_derived(client, ingestion_on, conn_headers, db):
    """Phase 2 stores events only. The punch table has no IN/OUT, session or
    duration column, and nothing populates one."""
    columns = set(BiometricPunch.__table__.columns.keys())
    forbidden = {
        "direction",
        "punch_direction",
        "is_in",
        "is_out",
        "session_id",
        "session_start",
        "session_end",
        "worked_minutes",
        "working_minutes",
        "duration_minutes",
        "overtime_minutes",
        "outside_minutes",
        "late_minutes",
        "attendance_status",
    }
    assert columns & forbidden == set()
