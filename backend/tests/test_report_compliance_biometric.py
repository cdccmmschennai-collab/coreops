"""Report compliance counts a punch-derived Present day as a worked day.

The gap this closes: compliance read `attendance_records` only, so an employee
whose day is Present purely because they badged in and out was invisible to it -
no logout prompt, no banner, no pending day. That is the majority case, since
most Present days are never typed in by anyone.

The rule that must NOT bend: a human's ruling still wins. A day somebody marked
leave stays leave even with punches on it, so an approved absence never starts
demanding a work report.

    docker exec wms-backend-1 pytest tests/test_report_compliance_biometric.py
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.biometric.models import BiometricEmployeeMapping, BiometricPunch
from app.modules.report_compliance.service import (
    _attendance_work_fraction,
    employee_compliance,
)
from app.modules.users.models import UserRole

IST_OFFSET = timedelta(hours=5, minutes=30)
CODE = "9100"


@pytest.fixture()
def employee(make_user, make_employee):
    u = make_user("emp@x.com", role=UserRole.employee)
    return make_employee(employee_code="EMP069", user_id=u.id), u


@pytest.fixture()
def punched(db, employee):
    """Map the employee's device code and give them a full punch pair on a day."""
    emp, _ = employee
    db.add(
        BiometricEmployeeMapping(
            provider="easytime",
            external_employee_code=CODE,
            employee_id=emp.id,
            is_active=True,
        )
    )
    db.commit()
    counter = {"n": 0}

    def _punch(day: date, hh: int, mm: int) -> None:
        counter["n"] += 1
        db.add(
            BiometricPunch(
                provider="easytime",
                external_transaction_id=f"txn-{counter['n']}",
                external_employee_code=CODE,
                employee_id=None,
                punch_time=datetime(
                    day.year, day.month, day.day, hh, mm, tzinfo=timezone(IST_OFFSET)
                ),
                received_at=datetime.now(timezone.utc),
                raw_punch_state="0",
            )
        )
        db.commit()

    def _full_day(day: date) -> None:
        _punch(day, 9, 10)
        _punch(day, 17, 54)

    return {"punch": _punch, "full_day": _full_day}


# ── the reported bug ───────────────────────────────────────────────────────

def test_punches_alone_make_today_a_worked_day(db, employee, punched):
    """The logout guard reads `has_attendance_today`. With no attendance record
    and a full punch pair it must be True - the employee IS present."""
    emp, user = employee
    punched["full_day"](date.today())

    snapshot = employee_compliance(db, user)
    assert snapshot["has_attendance_today"] is True
    assert snapshot["has_report_today"] is False


def test_one_punch_is_not_a_worked_day(db, employee, punched):
    """`incomplete` settles nothing. Demanding a report on one unpaired swipe
    would be a guess about whether they stayed."""
    punched["punch"](date.today(), 9, 10)
    _, user = employee

    assert employee_compliance(db, user)["has_attendance_today"] is False


def test_no_punches_and_no_record_is_still_clear(db, employee):
    _, user = employee
    snapshot = employee_compliance(db, user)
    assert snapshot["has_attendance_today"] is False
    assert snapshot["pending_count"] == 0


# ── a human's ruling still wins ────────────────────────────────────────────

def test_a_leave_day_with_punches_does_not_demand_a_report(db, employee, punched):
    """The 12 August shape: punches on the day, and somebody ruled it leave.
    The ruling is the answer - no report is owed."""
    emp, user = employee
    today = date.today()
    punched["full_day"](today)
    db.add(
        AttendanceRecord(
            employee_id=emp.id,
            attendance_date=today,
            status=AttendanceStatus.leave,
            total_minutes=0,
            overtime_minutes=0,
        )
    )
    db.commit()

    snapshot = employee_compliance(db, user)
    assert snapshot["has_attendance_today"] is False
    assert snapshot["attendance_work_fraction_today"] is None


def test_a_half_day_record_beats_the_punches(db, employee, punched):
    """A PM's half day stays 0.5 - the device cannot express a half day and must
    not silently promote the ruling to a whole one."""
    emp, user = employee
    today = date.today()
    punched["full_day"](today)
    db.add(
        AttendanceRecord(
            employee_id=emp.id,
            attendance_date=today,
            status=AttendanceStatus.half_day,
            total_minutes=0,
            overtime_minutes=0,
        )
    )
    db.commit()

    snapshot = employee_compliance(db, user)
    assert snapshot["has_attendance_today"] is True
    assert snapshot["attendance_work_fraction_today"] == 0.5


# ── the fraction rule, directly ────────────────────────────────────────────

@pytest.mark.parametrize(
    "status, biometric_present, expected",
    [
        (AttendanceStatus.present, False, 1.0),
        (AttendanceStatus.half_day, False, 0.5),
        (AttendanceStatus.half_day, True, 0.5),
        (AttendanceStatus.leave, True, None),
        (AttendanceStatus.absent, True, None),
        (None, True, 1.0),
        (None, False, None),
    ],
)
def test_work_fraction_prefers_the_ruling_then_the_device(
    status, biometric_present, expected
):
    assert (
        _attendance_work_fraction(status, biometric_present=biometric_present)
        == expected
    )
