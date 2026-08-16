"""Phase 9C - GET /biometric/daily-summary: the employee Calendar must show
the SAME finalized result (device + PM-decision merge) the PM Records/detail
screens already show, not raw biometric evidence alone.

Scoped to exactly what Phase 9C changed in `list_daily_summary` - the
pre-existing pure-biometric behavior is already covered by
test_biometric_daily_summary.py and is not re-tested here.
"""
from datetime import datetime, timezone

import pytest

from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.users.models import UserRole

SUMMARY = "/api/v1/biometric/daily-summary"
ATTEND = "/api/v1/attendance"
DAY = "2026-08-10"


@pytest.fixture()
def pm(auth_header):
    return auth_header("pm-cal-merge@x.com", role=UserRole.project_manager)


def _punch(db, *, code: str, hour: int, minute: int = 0):
    db.add(
        BiometricPunch(
            provider="easytime",
            external_transaction_id=f"txn-{code}-{hour}-{minute}",
            external_employee_code=code,
            employee_id=None,
            punch_time=datetime(2026, 8, 10, hour, minute, tzinfo=timezone.utc),
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


def _summary_row(client, pm, employee_id, date=DAY):
    res = client.get(
        SUMMARY, params={"employee_id": str(employee_id), "from": date, "to": date}, headers=pm
    )
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    return items[0] if items else None


def test_zero_punches_with_a_pm_decision_now_produces_a_row(client, pm, db, make_employee):
    """CASE 3: no biometric punches, PM enters both - previously silent."""
    emp = make_employee(employee_code="C001", first_name="Zero", last_name="Punch")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:40:00+05:30",
            "check_out_at": f"{DAY}T16:46:00+05:30",
            "note": "No punch, PM recorded.",
        },
    )
    assert create.status_code == 201, create.text

    row = _summary_row(client, pm, emp.id)
    assert row is not None, "a PM-decided day must not be silently absent"
    assert row["first_in_source"] == "pm"
    assert row["last_out_source"] == "pm"
    assert row["first_in"] is not None
    assert row["last_out"] is not None
    assert row["worked_minutes"] == 7 * 60 + 6
    # Biometric evidence is untouched by the decision - still nothing seen.
    assert row["punch_count"] == 0
    assert row["kept_count"] == 0
    assert row["classification"] == "no_record"


def test_one_device_punch_plus_pm_completion_keeps_device_value(client, pm, db, make_employee):
    """CASE 2: device has IN only, PM fills OUT - IN must stay the device value."""
    emp = make_employee(employee_code="C002", first_name="One", last_name="Punch")
    _map(db, emp, code="C002")
    _punch(db, code="C002", hour=3, minute=35)  # 09:05 IST, device

    update = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "present",
            "check_in_at": f"{DAY}T09:05:00+05:30",
            "check_out_at": f"{DAY}T17:30:00+05:30",
            "note": None,
        },
    )
    assert update.status_code == 201, update.text

    row = _summary_row(client, pm, emp.id)
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "pm"
    assert row["punch_count"] == 1
    assert row["kept_count"] == 1
    assert row["classification"] == "incomplete"  # evidence alone is still one sighting


def test_two_device_punches_are_unaffected_by_the_merge(client, pm, db, make_employee):
    """CASE 1: full device evidence, no attendance_records row at all."""
    emp = make_employee(employee_code="C003", first_name="Two", last_name="Punch")
    _map(db, emp, code="C003")
    _punch(db, code="C003", hour=3, minute=48)   # 09:18 IST
    _punch(db, code="C003", hour=12, minute=7)   # 17:37 IST

    row = _summary_row(client, pm, emp.id)
    assert row["first_in_source"] == "device"
    assert row["last_out_source"] == "device"
    assert row["classification"] == "present"


def test_leave_with_no_times_entered_reports_no_boundary_but_still_a_row(
    client, pm, db, make_employee
):
    """A Leave decision with no punch and no PM-entered time must not fabricate
    a boundary, but the day must still surface (e.g. for Scheduled)."""
    emp = make_employee(employee_code="C004", first_name="Leave", last_name="Day")
    create = client.post(
        ATTEND,
        headers=pm,
        json={
            "employee_id": str(emp.id),
            "attendance_date": DAY,
            "status": "leave",
            "check_in_at": None,
            "check_out_at": None,
            "note": "Approved leave.",
        },
    )
    assert create.status_code == 201, create.text

    row = _summary_row(client, pm, emp.id)
    assert row is not None
    assert row["first_in"] is None
    assert row["last_out"] is None
    assert row["first_in_source"] is None
    assert row["last_out_source"] is None
    assert row["scheduled_minutes"] is not None


def test_a_day_with_neither_punches_nor_a_decision_is_still_silent(client, pm, db, make_employee):
    """Nothing to report is still nothing - no synthetic row is invented."""
    emp = make_employee(employee_code="C005", first_name="Nothing", last_name="Here")
    row = _summary_row(client, pm, emp.id)
    assert row is None
