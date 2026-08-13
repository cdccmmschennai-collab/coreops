"""Phase 5 - employee mapping management (no migration; 0066 tables only).

Covers the external-code operations view, the reviewed bulk import, and the
guarantees that must survive all of it: raw punches are never rewritten, CoreOps
never proposes an employee for a code, and only a project manager can touch any
of this.

Every assertion is database-backed through the `db` fixture.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.modules.audit.constants import AuditAction
from app.modules.audit.models import AuditLog
from app.modules.biometric.constants import (
    BULK_DUPLICATE_CODE_IN_REQUEST,
    BULK_DUPLICATE_EMPLOYEE_IN_REQUEST,
    BULK_EMPLOYEE_MAPPED_TO_OTHER_CODE,
    BULK_EMPLOYEE_NOT_FOUND,
    BULK_REMAP_NOT_ALLOWED,
    CODE_STATUS_MAPPED,
    CODE_STATUS_UNMAPPED,
)
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.employees.models import EmployeeStatus
from app.modules.users.models import UserRole

CODES = "/api/v1/biometric/external-codes"
MAPPINGS = "/api/v1/biometric/mappings"
BULK = "/api/v1/biometric/mappings/bulk"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def punch(db):
    """Insert a raw punch directly.

    Deliberately NOT through the ingestion endpoint: Phase 5 is about codes
    that are already stored, including codes stored long before any mapping
    existed, which is exactly the state the production backfill left behind.
    """
    counter = {"n": 0}

    def _make(
        code: str,
        *,
        when: datetime | None = None,
        employee_id: uuid.UUID | None = None,
        provider: str = "easytime",
    ) -> BiometricPunch:
        counter["n"] += 1
        row = BiometricPunch(
            provider=provider,
            external_transaction_id=f"txn-{counter['n']}",
            external_employee_code=code,
            employee_id=employee_id,
            punch_time=when or datetime(2026, 7, 29, 4, 42, tzinfo=timezone.utc),
            received_at=datetime.now(timezone.utc),
            raw_punch_state="0",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return row

    return _make


def _codes(client, pm, **params):
    res = client.get(CODES, params=params, headers=pm)
    assert res.status_code == 200, res.text
    return res.json()


def _by_code(payload) -> dict:
    return {i["external_employee_code"]: i for i in payload["items"]}


# ── the external-code view ──────────────────────────────────────────────────

def test_distinct_codes_with_counts_and_window(client, pm, punch):
    early = datetime(2026, 7, 29, 4, 42, tzinfo=timezone.utc)
    late = datetime(2026, 8, 11, 12, 30, tzinfo=timezone.utc)
    punch("61", when=early)
    punch("61", when=late)
    punch("62", when=early)

    body = _codes(client, pm)
    rows = _by_code(body)

    assert body["total"] == 2
    assert rows["61"]["punch_count"] == 2
    assert rows["62"]["punch_count"] == 1
    assert rows["61"]["first_seen"].startswith("2026-07-29")
    assert rows["61"]["last_seen"].startswith("2026-08-11")


def test_summary_counts_cover_the_whole_provider(client, pm, punch, make_employee):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    punch("62")
    punch("63")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )

    # Even a filtered, paginated request reports the provider-wide totals.
    body = _codes(client, pm, status=CODE_STATUS_UNMAPPED, limit=1)
    assert body["total_codes"] == 3
    assert body["mapped_codes"] == 1
    assert body["unmapped_codes"] == 2
    assert body["total"] == 2  # filtered
    assert len(body["items"]) == 1  # paginated


def test_mapped_code_reports_the_employee(client, pm, punch, make_employee):
    emp = make_employee(employee_code="EMP061", first_name="Asha", last_name="R")
    punch("61")
    created = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    ).json()

    row = _by_code(_codes(client, pm))["61"]
    assert row["status"] == CODE_STATUS_MAPPED
    assert row["mapping_id"] == created["id"]
    assert row["employee_code"] == "EMP061"
    assert row["employee_name"] == "Asha R"
    assert row["verified_at"] is not None


def test_status_filter(client, pm, punch, make_employee):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    punch("62")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )

    mapped = _by_code(_codes(client, pm, status=CODE_STATUS_MAPPED))
    unmapped = _by_code(_codes(client, pm, status=CODE_STATUS_UNMAPPED))
    assert list(mapped) == ["61"]
    assert list(unmapped) == ["62"]


def test_search_matches_code_and_employee(client, pm, punch, make_employee):
    emp = make_employee(employee_code="EMP061", first_name="Asha", last_name="Rao")
    punch("61")
    punch("62")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )

    assert list(_by_code(_codes(client, pm, q="62"))) == ["62"]
    assert list(_by_code(_codes(client, pm, q="Asha"))) == ["61"]
    assert list(_by_code(_codes(client, pm, q="EMP061"))) == ["61"]


def test_codes_are_ordered_numerically_not_lexicographically(client, pm, punch):
    for code in ("1001", "59", "091", "215"):
        punch(code)
    body = _codes(client, pm)
    assert [i["external_employee_code"] for i in body["items"]] == [
        "59",
        "091",
        "215",
        "1001",
    ]


def test_bad_status_filter_rejected(client, pm):
    assert client.get(CODES, params={"status": "nope"}, headers=pm).status_code == 422


def test_unsupported_provider_rejected(client, pm):
    assert client.get(CODES, params={"provider": "zkteco"}, headers=pm).status_code == 422


def test_external_codes_is_pm_only(client, auth_header):
    emp_header = auth_header("emp@x.com", role=UserRole.employee)
    assert client.get(CODES, headers=emp_header).status_code == 403


def test_external_codes_requires_auth(client):
    assert client.get(CODES).status_code == 401


def test_view_writes_nothing(client, pm, punch, db):
    punch("61")
    before = db.execute(select(BiometricPunch)).scalar_one()
    stored = (before.employee_id, before.punch_time, before.created_at)

    _codes(client, pm)

    db.expire_all()
    after = db.execute(select(BiometricPunch)).scalar_one()
    assert (after.employee_id, after.punch_time, after.created_at) == stored
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


# ── CoreOps proposes nothing ────────────────────────────────────────────────
# There is no suggestion tier, no code normalization and no name comparison.
# These tests exist to keep it that way: an inferred pairing must not creep back
# in as a convenience.

def test_the_view_never_returns_a_suggestion(client, pm, punch, make_employee):
    # The textbook "obvious" pairing: EMP061 and EasyTime 61. Still not proposed.
    make_employee(employee_code="EMP061", first_name="Asha", last_name="Rao")
    punch("61")

    row = _by_code(_codes(client, pm))["61"]
    assert "suggestion" not in row
    # And no employee is named, because no mapping row exists.
    assert row["employee_id"] is None
    assert row["employee_code"] is None
    assert row["employee_name"] is None
    assert row["status"] == CODE_STATUS_UNMAPPED


def test_a_name_shaped_code_is_never_matched_to_an_employee(
    client, pm, punch, make_employee
):
    make_employee(employee_code="X99", first_name="Ravi", last_name="Kumar")
    punch("Ravi Kumar")

    row = _by_code(_codes(client, pm))["Ravi Kumar"]
    assert row["employee_id"] is None
    assert "suggestion" not in row


def test_an_ambiguous_code_is_simply_unmapped(client, pm, punch, make_employee, db):
    # EM001 and MGR-001 both "look like" 1. Nothing decides between them, and
    # nothing is written - the PM chooses.
    make_employee(employee_code="EM001")
    make_employee(employee_code="MGR-001")
    punch("1")

    row = _by_code(_codes(client, pm))["1"]
    assert row["status"] == CODE_STATUS_UNMAPPED
    assert row["employee_id"] is None
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


def test_leading_zero_code_is_stored_and_returned_verbatim(
    client, pm, punch, make_employee, db
):
    make_employee(employee_code="EMP091")
    punch("091")

    row = _by_code(_codes(client, pm))["091"]
    # The code is never coerced to a number anywhere: "091" stays "091".
    assert row["external_employee_code"] == "091"
    assert db.execute(
        select(BiometricPunch.external_employee_code)
    ).scalar_one() == "091"
    # EMP091 is NOT offered for it.
    assert row["employee_id"] is None


def test_reading_the_view_writes_no_mapping(client, pm, punch, make_employee, db):
    make_employee(employee_code="EMP061")
    punch("61")
    _codes(client, pm)
    _codes(client, pm)
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


# ── the exact-code ingestion fallback, reported honestly ─────────────────────

def test_exact_code_match_is_flagged_as_already_resolving(
    client, pm, punch, make_employee
):
    make_employee(employee_code="61")
    punch("61")
    row = _by_code(_codes(client, pm))["61"]
    # No mapping row exists, yet ingestion would resolve this code on its own,
    # so reporting a bare "unmapped" would mislead the PM.
    assert row["status"] == CODE_STATUS_UNMAPPED
    assert row["resolves_by_exact_code"] is True


def test_exact_code_flag_matches_ingestion_for_an_exited_employee(
    client, pm, punch, make_employee
):
    # Ingestion's fallback filters on deleted_at only, NOT on status, so this
    # flag must not filter on status either - the two must never disagree.
    make_employee(employee_code="61", status=EmployeeStatus.exited)
    punch("61")
    assert _by_code(_codes(client, pm))["61"]["resolves_by_exact_code"] is True


def test_a_near_miss_code_is_not_flagged_as_resolving(client, pm, punch, make_employee):
    make_employee(employee_code="EMP061")
    punch("61")
    assert _by_code(_codes(client, pm))["61"]["resolves_by_exact_code"] is False


# ── mapping lifecycle over historical punches ───────────────────────────────

def test_mapping_a_code_does_not_rewrite_existing_punches(
    client, pm, punch, make_employee, db
):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    punch("61")

    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )

    db.expire_all()
    rows = db.execute(select(BiometricPunch)).scalars().all()
    # Raw punches are immutable. Historical attribution comes from the mapping
    # table when a later phase calculates, never from an UPDATE here.
    assert [r.employee_id for r in rows] == [None, None]

    view = _by_code(_codes(client, pm))["61"]
    assert view["status"] == CODE_STATUS_MAPPED
    assert view["punch_count"] == 2
    assert view["attributed_punch_count"] == 0


def test_remap_deactivates_the_previous_row(client, pm, punch, make_employee, db):
    first = make_employee(employee_code="EMP061")
    second = make_employee(employee_code="EMP069")
    punch("61")
    body = {"provider": "easytime", "external_employee_code": "61"}

    client.post(MAPPINGS, json={**body, "employee_id": str(first.id)}, headers=pm)
    client.post(MAPPINGS, json={**body, "employee_id": str(second.id)}, headers=pm)

    rows = db.execute(
        select(BiometricEmployeeMapping).order_by(BiometricEmployeeMapping.created_at)
    ).scalars().all()
    assert [r.is_active for r in rows] == [False, True]
    assert _by_code(_codes(client, pm))["61"]["employee_code"] == "EMP069"


def test_deactivate_returns_the_code_to_unmapped(client, pm, punch, make_employee):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    created = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    ).json()

    assert client.delete(f"{MAPPINGS}/{created['id']}", headers=pm).status_code == 200
    row = _by_code(_codes(client, pm))["61"]
    assert row["status"] == CODE_STATUS_UNMAPPED
    assert row["employee_id"] is None


def test_creating_the_same_mapping_twice_is_idempotent(
    client, pm, punch, make_employee, db
):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    body = {
        "provider": "easytime",
        "external_employee_code": "61",
        "employee_id": str(emp.id),
    }
    first = client.post(MAPPINGS, json=body, headers=pm)
    second = client.post(MAPPINGS, json=body, headers=pm)

    assert first.json()["id"] == second.json()["id"]
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 1
    # One creation, one audit row - a no-op write must not forge history.
    assert db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == AuditAction.BIOMETRIC_MAPPING_CREATED)
    ).scalar_one() == 1


# ── bulk import ─────────────────────────────────────────────────────────────

def _bulk(client, pm, items, **over):
    body = {"provider": "easytime", "items": items}
    body.update(over)
    return client.post(BULK, json=body, headers=pm)


def test_bulk_creates_every_confirmed_mapping(client, pm, punch, make_employee, db):
    a = make_employee(employee_code="EMP061")
    b = make_employee(employee_code="EMP069")
    punch("61")
    punch("69")

    res = _bulk(
        client,
        pm,
        [
            {"external_employee_code": "61", "employee_id": str(a.id)},
            {"external_employee_code": "69", "employee_id": str(b.id)},
        ],
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["requested"], body["mapped"], body["skipped"]) == (2, 2, 0)
    assert db.execute(
        select(func.count())
        .select_from(BiometricEmployeeMapping)
        .where(BiometricEmployeeMapping.is_active.is_(True))
    ).scalar_one() == 2


def test_bulk_counts_always_add_up(client, pm, make_employee):
    a = make_employee(employee_code="EMP061")
    res = _bulk(
        client,
        pm,
        [
            {"external_employee_code": "61", "employee_id": str(a.id)},
            {"external_employee_code": "62", "employee_id": str(uuid.uuid4())},
        ],
    ).json()
    assert res["mapped"] + res["unchanged"] + res["skipped"] == res["requested"]
    assert len(res["items"]) == res["requested"]


def test_bulk_is_idempotent(client, pm, make_employee, db):
    a = make_employee(employee_code="EMP061")
    items = [{"external_employee_code": "61", "employee_id": str(a.id)}]
    _bulk(client, pm, items)
    second = _bulk(client, pm, items).json()

    assert (second["mapped"], second["unchanged"]) == (0, 1)
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 1


def test_bulk_skips_an_unknown_employee_without_writing(client, pm, make_employee, db):
    good = make_employee(employee_code="EMP061")
    res = _bulk(
        client,
        pm,
        [
            {"external_employee_code": "61", "employee_id": str(good.id)},
            {"external_employee_code": "62", "employee_id": str(uuid.uuid4())},
        ],
    ).json()

    reasons = {i["external_employee_code"]: i["reason"] for i in res["items"]}
    assert reasons["62"] == BULK_EMPLOYEE_NOT_FOUND
    assert res["mapped"] == 1
    # The good half still landed; a bad row does not poison the batch.
    assert db.execute(
        select(BiometricEmployeeMapping.external_employee_code)
    ).scalar_one() == "61"


def test_bulk_skips_a_deleted_employee(client, pm, make_employee, db):
    emp = make_employee(employee_code="EMP061")
    emp.deleted_at = datetime.now(timezone.utc)
    db.add(emp)
    db.commit()

    res = _bulk(
        client, pm, [{"external_employee_code": "61", "employee_id": str(emp.id)}]
    ).json()
    assert res["items"][0]["reason"] == BULK_EMPLOYEE_NOT_FOUND
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


def test_bulk_refuses_a_code_listed_twice(client, pm, make_employee, db):
    a = make_employee(employee_code="EMP061")
    b = make_employee(employee_code="EMP069")
    res = _bulk(
        client,
        pm,
        [
            {"external_employee_code": "61", "employee_id": str(a.id)},
            {"external_employee_code": "61", "employee_id": str(b.id)},
        ],
    ).json()

    assert res["skipped"] == 2
    assert {i["reason"] for i in res["items"]} == {BULK_DUPLICATE_CODE_IN_REQUEST}
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


def test_bulk_refuses_an_employee_listed_twice(client, pm, make_employee, db):
    a = make_employee(employee_code="EMP091")
    # "091" and "91" are two DIFFERENT device codes. Pointing both at one
    # employee in a single request is almost certainly an operator slip.
    res = _bulk(
        client,
        pm,
        [
            {"external_employee_code": "091", "employee_id": str(a.id)},
            {"external_employee_code": "91", "employee_id": str(a.id)},
        ],
    ).json()

    assert res["skipped"] == 2
    assert {i["reason"] for i in res["items"]} == {BULK_DUPLICATE_EMPLOYEE_IN_REQUEST}
    assert db.execute(
        select(func.count()).select_from(BiometricEmployeeMapping)
    ).scalar_one() == 0


def test_bulk_refuses_an_employee_already_mapped_elsewhere(client, pm, make_employee):
    emp = make_employee(employee_code="EMP061")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(emp.id),
        },
        headers=pm,
    )
    res = _bulk(
        client, pm, [{"external_employee_code": "1061", "employee_id": str(emp.id)}]
    ).json()
    assert res["items"][0]["reason"] == BULK_EMPLOYEE_MAPPED_TO_OTHER_CODE
    assert res["mapped"] == 0


def test_bulk_will_not_repoint_a_code_by_default(client, pm, make_employee, db):
    first = make_employee(employee_code="EMP061")
    second = make_employee(employee_code="EMP069")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(first.id),
        },
        headers=pm,
    )

    res = _bulk(
        client, pm, [{"external_employee_code": "61", "employee_id": str(second.id)}]
    ).json()
    assert res["items"][0]["reason"] == BULK_REMAP_NOT_ALLOWED

    active = db.execute(
        select(BiometricEmployeeMapping).where(
            BiometricEmployeeMapping.is_active.is_(True)
        )
    ).scalar_one()
    assert active.employee_id == first.id


def test_bulk_repoints_when_explicitly_allowed(client, pm, make_employee, db):
    first = make_employee(employee_code="EMP061")
    second = make_employee(employee_code="EMP069")
    client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(first.id),
        },
        headers=pm,
    )

    res = _bulk(
        client,
        pm,
        [{"external_employee_code": "61", "employee_id": str(second.id)}],
        allow_remap=True,
    ).json()
    assert res["mapped"] == 1

    rows = db.execute(
        select(BiometricEmployeeMapping).order_by(BiometricEmployeeMapping.created_at)
    ).scalars().all()
    assert [r.is_active for r in rows] == [False, True]
    assert rows[1].employee_id == second.id


def test_bulk_audits_every_mapping_it_writes(client, pm, make_employee, db):
    a = make_employee(employee_code="EMP061")
    b = make_employee(employee_code="EMP069")
    _bulk(
        client,
        pm,
        [
            {"external_employee_code": "61", "employee_id": str(a.id)},
            {"external_employee_code": "69", "employee_id": str(b.id)},
        ],
    )
    rows = db.execute(
        select(AuditLog).where(
            AuditLog.action == AuditAction.BIOMETRIC_MAPPING_CREATED
        )
    ).scalars().all()
    assert {r.details["external_employee_code"] for r in rows} == {"61", "69"}


def test_bulk_does_not_audit_a_skipped_item(client, pm, make_employee, db):
    _bulk(
        client,
        pm,
        [{"external_employee_code": "61", "employee_id": str(uuid.uuid4())}],
    )
    assert db.execute(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == AuditAction.BIOMETRIC_MAPPING_CREATED)
    ).scalar_one() == 0


def test_bulk_preserves_leading_zero_codes(client, pm, make_employee, db):
    emp = make_employee(employee_code="EMP091")
    _bulk(client, pm, [{"external_employee_code": "091", "employee_id": str(emp.id)}])
    assert db.execute(
        select(BiometricEmployeeMapping.external_employee_code)
    ).scalar_one() == "091"


def test_bulk_never_rewrites_raw_punches(client, pm, punch, make_employee, db):
    emp = make_employee(employee_code="EMP061")
    punch("61")
    _bulk(client, pm, [{"external_employee_code": "61", "employee_id": str(emp.id)}])

    db.expire_all()
    assert db.execute(select(BiometricPunch.employee_id)).scalar_one() is None


def test_bulk_is_pm_only(client, auth_header, make_employee):
    emp = make_employee(employee_code="EMP061")
    emp_header = auth_header("emp@x.com", role=UserRole.employee)
    res = client.post(
        BULK,
        json={
            "provider": "easytime",
            "items": [{"external_employee_code": "61", "employee_id": str(emp.id)}],
        },
        headers=emp_header,
    )
    assert res.status_code == 403, res.text


def test_bulk_requires_auth(client):
    assert client.post(BULK, json={"provider": "easytime", "items": []}).status_code == 401


def test_bulk_rejects_an_empty_or_unsupported_request(client, pm, make_employee):
    emp = make_employee(employee_code="EMP061")
    assert _bulk(client, pm, []).status_code == 422
    assert client.post(
        BULK,
        json={
            "provider": "zkteco",
            "items": [{"external_employee_code": "61", "employee_id": str(emp.id)}],
        },
        headers=pm,
    ).status_code == 422


# ── isolation guarantees ────────────────────────────────────────────────────

def test_mapping_ids_are_never_assumed_across_databases(client, pm, make_employee):
    """A mapping is created from an employee id resolved in THIS database.

    The API accepts no employee CODE as a mapping target, so a mapping cannot
    be replayed from another environment by code and silently bind to whatever
    row happens to hold that id. An id that is not present here is rejected -
    which is exactly what makes copying local mappings into production fail
    loudly instead of mis-attributing somebody's attendance.
    """
    foreign_id = uuid.uuid4()
    res = client.post(
        MAPPINGS,
        json={
            "provider": "easytime",
            "external_employee_code": "61",
            "employee_id": str(foreign_id),
        },
        headers=pm,
    )
    assert res.status_code == 422, res.text

    make_employee(employee_code="EMP061")
    bulk = _bulk(
        client, pm, [{"external_employee_code": "61", "employee_id": str(foreign_id)}]
    ).json()
    assert bulk["items"][0]["reason"] == BULK_EMPLOYEE_NOT_FOUND


def test_other_provider_punches_are_not_listed(client, pm, punch):
    punch("61")
    punch("77", provider="other")
    assert list(_by_code(_codes(client, pm))) == ["61"]


def test_phase5_derives_no_attendance(client, pm, punch, make_employee, db):
    """Phase 5 maps identities. It does not pair punches or invent a session."""
    from app.modules.attendance.models import AttendanceRecord

    emp = make_employee(employee_code="EMP061")
    now = datetime(2026, 7, 29, 4, 0, tzinfo=timezone.utc)
    punch("61", when=now)
    punch("61", when=now + timedelta(hours=9))
    _bulk(client, pm, [{"external_employee_code": "61", "employee_id": str(emp.id)}])
    _codes(client, pm)

    assert db.execute(
        select(func.count()).select_from(AttendanceRecord)
    ).scalar_one() == 0
