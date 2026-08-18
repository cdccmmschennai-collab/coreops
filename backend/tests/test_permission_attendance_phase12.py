"""Phase 12 - APPROVED permission joined to the attendance presentation.

THE RULE UNDER TEST
===================
An approved 1h or 2h permission does NOT replace an employee's biometric
attendance. It is an ADDITIONAL attribute of that date:

    biometric   05:13 - 21:30   worked 16h 17m
    permission  2 hours
    display     Present | 2hr - 16h 17m

So every test here asks one of two questions:

  1. is the approved permission - and ONLY the approved permission - reported
     for the right employee-day?
  2. did anything about the biometric evidence, the worked duration or the
     official attendance decision change because of it?

The answer to (2) must always be "no", which is why the tests capture the whole
row BEFORE the permission exists and compare field by field afterwards rather
than asserting hard-coded times: a comparison against the actual prior value
catches a regression that a hand-written expected value would sail past.

Nothing here re-tests Phase 11. The 4h monthly allowance, the approval guard and
the cancellation restore are covered by test_permissions_phase11.py and remain
the only source of truth for the balance.

    docker exec wms-backend-1 pytest tests/test_permission_attendance_phase12.py
"""
from datetime import date, datetime, timezone

import pytest

from app.modules.attendance.models import AttendanceStatus
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import UserRole

SUMMARY = "/api/v1/biometric/daily-summary"
REVIEW = "/api/v1/biometric/daily-review"
ATTEND = "/api/v1/attendance"
PERMISSIONS = "/api/v1/permission-requests"

# Monday 10 August 2026 - a past working day, so `/daily-review` (which refuses
# a future date) accepts it and the punches below are plausible history.
DAY = date(2026, 8, 10)
DAY_ISO = DAY.isoformat()
OTHER_DAY = date(2026, 8, 11)

# The biometric fields that must be IDENTICAL with and without a permission.
# Listed explicitly rather than diffing the whole row, because `permission_hours`
# itself is the one key that is expected to differ.
BIOMETRIC_FIELDS = (
    "first_in",
    "last_out",
    "first_in_source",
    "last_out_source",
    "worked_minutes",
    "punch_count",
    "kept_count",
    "punch_times",
    "scheduled_minutes",
    "classification",
    "review_required",
)


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-phase12@x.com", role=UserRole.project_manager)


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="P12A", first_name="Santhosh", last_name="Kumar")


def _punch(db, *, code: str, when: datetime):
    db.add(
        BiometricPunch(
            provider="easytime",
            external_transaction_id=f"txn-{code}-{when.isoformat()}",
            external_employee_code=code,
            employee_id=None,
            punch_time=when,
            received_at=datetime.now(timezone.utc),
            raw_punch_state="0",
        )
    )
    db.commit()


def _map(db, employee, *, code: str):
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=code,
            employee_id=employee.id,
            is_active=True,
        )
    )
    db.commit()


def _worked_day(db, employee, *, code: str):
    """A full biometric day: 06:00 IST in, 21:30 IST out (00:30 / 16:00 UTC)."""
    _map(db, employee, code=code)
    _punch(db, code=code, when=datetime(2026, 8, 10, 0, 30, tzinfo=timezone.utc))
    _punch(db, code=code, when=datetime(2026, 8, 10, 16, 0, tzinfo=timezone.utc))


def _summary_row(client, pm, employee_id, day: date = DAY):
    res = client.get(
        SUMMARY,
        params={"employee_id": str(employee_id), "from": day.isoformat(), "to": day.isoformat()},
        headers=pm,
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    return items[0] if items else None


def _review_row(client, pm, employee_id, day: date = DAY):
    res = client.get(REVIEW, params={"date": day.isoformat(), "limit": 100}, headers=pm)
    assert res.status_code == 200, res.text
    for row in res.json()["items"]:
        if row["employee_id"] == str(employee_id):
            return row
    return None


def _detail_row(client, pm, employee_id, day: date = DAY):
    res = client.get(
        f"{REVIEW}/{employee_id}", params={"date": day.isoformat()}, headers=pm
    )
    assert res.status_code == 200, res.text
    return res.json()["row"]


def _assert_biometric_unchanged(before: dict, after: dict):
    for field in BIOMETRIC_FIELDS:
        assert after[field] == before[field], f"{field} changed because of a permission"


def _stored_punches(db, employee_code: str):
    """The raw punch rows exactly as ingested - the evidence itself."""
    return sorted(
        (p.punch_time, p.raw_punch_state, p.employee_id)
        for p in db.query(BiometricPunch)
        .filter_by(external_employee_code=employee_code)
        .all()
    )


# ======================================================================
# Only APPROVED reaches attendance
# ======================================================================

@pytest.mark.parametrize(
    "status",
    [PermissionStatus.pending, PermissionStatus.rejected, PermissionStatus.cancelled],
)
def test_only_an_approved_permission_reaches_the_attendance_day(
    client, pm, db, employee, make_permission_request, status
):
    """Edge cases B, C and F. A request that was never granted, was refused, or
    was withdrawn is not an attendance fact, so the day reads exactly as it
    would with no permission request at all."""
    _worked_day(db, employee, code="P12A")
    make_permission_request(
        employee_id=employee.id, permission_date=DAY, duration_hours=2, status=status
    )

    assert _summary_row(client, pm, employee.id)["permission_hours"] is None
    assert _review_row(client, pm, employee.id)["permission_hours"] is None
    assert _detail_row(client, pm, employee.id)["permission_hours"] is None


def test_no_permission_at_all_reports_nothing(client, pm, db, employee):
    """Edge case A - the ordinary day. `null`, never `0`: nobody claimed zero
    hours, and a zero would render as a permission indicator reading "0hr"."""
    _worked_day(db, employee, code="P12A")
    assert _summary_row(client, pm, employee.id)["permission_hours"] is None


@pytest.mark.parametrize("hours", [1, 2])
def test_an_approved_permission_is_reported_for_its_date(
    client, pm, db, employee, make_permission_request, hours
):
    """Edge cases D and E. 1h and 2h are carried through as themselves - the
    presentation layer formats "1hr"/"2hr" from this number, so a wrong value
    here is the one thing the UI cannot correct for."""
    _worked_day(db, employee, code="P12A")
    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=hours,
        status=PermissionStatus.approved,
    )

    assert _summary_row(client, pm, employee.id)["permission_hours"] == hours
    assert _review_row(client, pm, employee.id)["permission_hours"] == hours
    assert _detail_row(client, pm, employee.id)["permission_hours"] == hours


def test_a_permission_does_not_leak_onto_a_neighbouring_date(
    client, pm, db, employee, make_permission_request
):
    """The join is on (employee, DATE). Tuesday's permission is not Monday's."""
    _worked_day(db, employee, code="P12A")
    make_permission_request(
        employee_id=employee.id,
        permission_date=OTHER_DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    assert _summary_row(client, pm, employee.id)["permission_hours"] is None


def test_a_permission_does_not_leak_onto_a_colleague(
    client, pm, db, employee, make_employee, make_permission_request
):
    """The join is on (EMPLOYEE, date) too."""
    other = make_employee(employee_code="P12B", first_name="Other", last_name="Person")
    _worked_day(db, employee, code="P12A")
    make_permission_request(
        employee_id=other.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )

    assert _summary_row(client, pm, employee.id)["permission_hours"] is None
    assert _review_row(client, pm, employee.id)["permission_hours"] is None
    assert _review_row(client, pm, other.id)["permission_hours"] == 2


# ======================================================================
# Biometric integrity - Section 8, the critical one
# ======================================================================

def test_biometric_evidence_is_identical_with_and_without_a_permission(
    client, pm, db, employee, make_permission_request
):
    """Edge case J, and Section 8 verbatim.

    Two hours of permission must not move a punch, shift a boundary or shorten
    the worked total. The row is captured BEFORE the permission exists and every
    biometric field is compared against that exact prior value, so nothing can
    pass by coincidence.
    """
    _worked_day(db, employee, code="P12A")
    before = _summary_row(client, pm, employee.id)
    punches_before = _stored_punches(db, "P12A")
    assert before["worked_minutes"] == 15 * 60 + 30  # 06:00 -> 21:30 IST

    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    after = _summary_row(client, pm, employee.id)

    _assert_biometric_unchanged(before, after)
    assert after["permission_hours"] == 2
    # The stored evidence itself, not just what the read reported.
    db.expire_all()
    assert _stored_punches(db, "P12A") == punches_before


def test_the_review_row_keeps_its_biometric_values_too(
    client, pm, db, employee, make_permission_request
):
    """The same guarantee on the PM Records path, which computes its row through
    a different function (`_review_row`) than the calendar does."""
    _worked_day(db, employee, code="P12A")
    before = _review_row(client, pm, employee.id)

    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=1,
        status=PermissionStatus.approved,
    )
    after = _review_row(client, pm, employee.id)

    for field in (
        "first_in",
        "last_out",
        "worked_minutes",
        "first_in_source",
        "last_out_source",
        "scheduled_minutes",
        "classification",
        "review_required",
        "can_set_check_in",
        "can_set_check_out",
        "review_reasons",
        "blocking_reasons",
    ):
        assert after[field] == before[field], f"{field} changed because of a permission"
    assert after["permission_hours"] == 1


def test_a_permission_with_no_punches_invents_no_biometric_times(
    client, pm, db, employee, make_permission_request
):
    """Edge case G. The day must be visible - otherwise the employee cannot see
    their approved permission at all - but it carries NO fabricated boundary."""
    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )

    row = _summary_row(client, pm, employee.id)
    assert row is not None, "an approved permission must not vanish from the calendar"
    assert row["permission_hours"] == 2
    assert row["first_in"] is None
    assert row["last_out"] is None
    assert row["worked_minutes"] is None
    assert row["punch_count"] == 0
    assert row["kept_count"] == 0
    assert row["punch_times"] == []
    # No cause is concluded from a permission: the evidence is still nothing.
    assert row["classification"] == "no_record"


def test_a_day_with_neither_punches_nor_a_permission_is_still_silent(
    client, pm, db, employee
):
    """The Phase 9C guarantee, re-pinned: nothing to report is still nothing."""
    assert _summary_row(client, pm, employee.id) is None


# ======================================================================
# The official attendance decision survives untouched
# ======================================================================

def test_a_pm_decided_day_keeps_its_decision_and_gains_the_permission(
    client, pm, db, employee, make_permission_request
):
    """Edge case H. The PM's ruling is the authoritative word for the day; the
    permission is added beside it and changes neither the status nor the times
    the PM entered."""
    _worked_day(db, employee, code="P12A")
    created = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(employee.id),
            "attendance_date": DAY_ISO,
            "status": "present",
            "check_in_at": f"{DAY_ISO}T09:00:00+05:30",
            "check_out_at": f"{DAY_ISO}T18:00:00+05:30",
            "note": "Settled by PM.",
        },
    )
    assert created.status_code == 201, created.text
    before = _review_row(client, pm, employee.id)

    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    after = _review_row(client, pm, employee.id)

    assert after["attendance_status"] == before["attendance_status"] == "present"
    assert after["attendance_note"] == before["attendance_note"] == "Settled by PM."
    assert after["attendance_record_id"] == before["attendance_record_id"]
    assert after["attendance_check_in_at"] == before["attendance_check_in_at"]
    assert after["attendance_check_out_at"] == before["attendance_check_out_at"]
    assert after["permission_hours"] == 2

    # And the stored record itself is untouched - status stays `present`, never
    # a new "permission" status.
    db.expire_all()
    from app.modules.attendance.models import AttendanceRecord

    record = db.query(AttendanceRecord).filter_by(
        employee_id=employee.id, attendance_date=DAY
    ).one()
    assert record.status == AttendanceStatus.present


# ======================================================================
# Cancellation
# ======================================================================

def test_cancelling_an_approved_permission_removes_it_from_the_day(
    client, pm, login, db, employee, make_permission_request
):
    """Edge case F, through the real Phase 11 endpoint.

    The day must return to EXACTLY its previous state - not "roughly present
    again". Because the presentation is derived rather than stored, cancelling
    writes nothing to attendance and there is nothing to undo.
    """
    _worked_day(db, employee, code="P12A")
    baseline = _summary_row(client, pm, employee.id)

    req = make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    assert _summary_row(client, pm, employee.id)["permission_hours"] == 2

    cancelled = client.post(f"{PERMISSIONS}/{req.id}/cancel", headers=pm, json={})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"

    after = _summary_row(client, pm, employee.id)
    assert after["permission_hours"] is None
    _assert_biometric_unchanged(baseline, after)
    assert _review_row(client, pm, employee.id)["permission_hours"] is None
    assert _detail_row(client, pm, employee.id)["permission_hours"] is None


def test_phase_11_balance_is_untouched_by_the_attendance_join(
    client, pm, login, make_user, make_employee, make_permission_request
):
    """Edge case K. Phase 12 reads permission rows; it does not count hours.

    The monthly figure still comes from Phase 11's derivation alone, and reading
    an attendance day never moves it.
    """
    user = make_user("p12-balance@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="P12C", user_id=user.id)
    make_permission_request(
        employee_id=emp.id,
        permission_date=DAY,
        duration_hours=2,
        status=PermissionStatus.approved,
    )

    before = client.get(
        f"{PERMISSIONS}/balance/me?month={DAY_ISO}", headers=login("p12-balance@x.com")
    ).json()
    assert (before["allowance_hours"], before["remaining_hours"]) == (4, 2)

    _summary_row(client, pm, emp.id)
    _review_row(client, pm, emp.id)

    after = client.get(
        f"{PERMISSIONS}/balance/me?month={DAY_ISO}", headers=login("p12-balance@x.com")
    ).json()
    assert after == before


# ======================================================================
# Phase 13 boundary - documented, not decided
# ======================================================================

def test_approved_leave_and_an_approved_permission_can_coexist_today(
    client, pm, db, employee, make_permission_request
):
    """DOCUMENTED CURRENT BEHAVIOR, NOT A PHASE 12 RULE.

    Phase 11 validates a permission against the working calendar only - it never
    consults leave - so an approved leave day can also carry an approved
    permission. Phase 12 reports both truthfully rather than inventing a
    resolution: the day keeps whatever attendance status it has (here `leave`)
    and the permission hours are attached beside it.

    Deciding what SHOULD happen - refuse the request, drop the permission, or
    flag the conflict - is Phase 13's, and this test exists so that when Phase 13
    changes the answer, the change is visible here rather than silent.
    """
    created = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(employee.id),
            "attendance_date": DAY_ISO,
            "status": "leave",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Approved leave.",
        },
    )
    assert created.status_code == 201, created.text
    make_permission_request(
        employee_id=employee.id,
        permission_date=DAY,
        duration_hours=1,
        status=PermissionStatus.approved,
    )

    row = _review_row(client, pm, employee.id)
    assert row["attendance_status"] == "leave"
    # The permission is NOT reclassified as leave and does not replace it.
    assert row["permission_hours"] == 1
    assert db.query(PermissionRequest).filter_by(
        employee_id=employee.id, permission_date=DAY, status=PermissionStatus.approved
    ).count() == 1
