"""`pending_dates` drives "Submit Pending Reports": the banner opens the New
report form at the EARLIEST entry, re-reading this list on every click. These
pin the contract that click relies on - ascending order, a submitted report
dropping out, drafts still owed, AUTO reports and non-working days excluded,
nothing from today or later, and nothing from another employee.

    docker exec wms-backend-1 pytest tests/test_report_compliance_pending_dates.py
"""
from datetime import date, timedelta

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.report_compliance.service import employee_compliance
from app.modules.users.models import UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportPeriod,
    WorkReportStatus,
)

TODAY = date.today()
# Three days strictly before today; always inside the current + previous month
# lookback since that window starts on the 1st of last month.
D1, D2, D3 = TODAY - timedelta(days=5), TODAY - timedelta(days=4), TODAY - timedelta(days=2)


@pytest.fixture()
def employee(make_user, make_employee):
    u = make_user("pending@x.com", role=UserRole.employee)
    return make_employee(employee_code="EMP801", user_id=u.id), u


def _attend(db, emp, day, status=AttendanceStatus.present):
    db.add(
        AttendanceRecord(
            employee_id=emp.id,
            attendance_date=day,
            status=status,
            total_minutes=0,
            overtime_minutes=0,
        )
    )
    db.commit()


def _report(db, emp, day, *, status=WorkReportStatus.submitted, origin=ReportOrigin.employee):
    report = DailyWorkReport(
        employee_id=emp.id,
        report_date=day,
        status=status,
        origin=origin,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        total_minutes=480,
    )
    db.add(report)
    db.commit()
    return report


def _pending(db, user):
    return employee_compliance(db, user)["pending_dates"]


def test_one_missing_date(db, employee):
    emp, user = employee
    _attend(db, emp, D1)
    assert _pending(db, user) == [D1]


def test_three_missing_dates_advance_as_reports_are_submitted(db, employee):
    emp, user = employee
    for d in (D3, D1, D2):  # inserted out of order on purpose
        _attend(db, emp, d)

    assert _pending(db, user) == [D1, D2, D3]
    _report(db, emp, D1)
    assert _pending(db, user) == [D2, D3]
    _report(db, emp, D2)
    assert _pending(db, user) == [D3]
    _report(db, emp, D3)
    snapshot = employee_compliance(db, user)
    assert snapshot["pending_dates"] == []
    assert snapshot["pending_count"] == 0


def test_a_draft_is_still_owed_until_it_is_submitted(db, employee):
    """The form then shows its existing "draft report for this date" notice and
    links to that draft - no second report is created."""
    emp, user = employee
    _attend(db, emp, D1)
    draft = _report(db, emp, D1, status=WorkReportStatus.draft)
    assert _pending(db, user) == [D1]

    draft.status = WorkReportStatus.submitted
    db.commit()
    assert _pending(db, user) == []


def test_an_auto_report_satisfies_the_day(db, employee):
    emp, user = employee
    _attend(db, emp, D1)
    _report(db, emp, D1, origin=ReportOrigin.auto)
    assert _pending(db, user) == []


@pytest.mark.parametrize(
    "status",
    [AttendanceStatus.leave, AttendanceStatus.absent, AttendanceStatus.holiday],
)
def test_non_working_days_are_never_pending(db, employee, status):
    emp, user = employee
    _attend(db, emp, D1, status=status)
    assert _pending(db, user) == []


def test_today_and_future_dates_are_never_pending(db, employee):
    emp, user = employee
    _attend(db, emp, TODAY)
    _attend(db, emp, TODAY + timedelta(days=1))
    assert _pending(db, user) == []


# ── reporting deadline: a day is due only from the following day ────────────

_OCT15, _OCT16, _OCT17 = date(2026, 10, 15), date(2026, 10, 16), date(2026, 10, 17)


def _on(monkeypatch, day):
    monkeypatch.setattr("app.modules.report_compliance.service._today", lambda: day)


def test_a_worked_day_is_not_pending_on_the_day_itself(db, employee, monkeypatch):
    """On 16 Oct, the 16 Oct report is still inside its window: it is owed
    (`has_report_today` False) but not pending."""
    emp, user = employee
    _attend(db, emp, _OCT16)
    _on(monkeypatch, _OCT16)

    snapshot = employee_compliance(db, user)
    assert snapshot["has_attendance_today"] is True
    assert snapshot["has_report_today"] is False
    assert snapshot["pending_dates"] == []
    assert snapshot["pending_count"] == 0


def test_the_day_becomes_pending_the_following_day(db, employee, monkeypatch):
    emp, user = employee
    _attend(db, emp, _OCT15)
    _attend(db, emp, _OCT16)

    _on(monkeypatch, _OCT16)
    assert _pending(db, user) == [_OCT15]

    _on(monkeypatch, _OCT17)
    assert _pending(db, user) == [_OCT15, _OCT16]


def test_submitting_on_the_grace_day_keeps_it_off_the_list(db, employee, monkeypatch):
    emp, user = employee
    _attend(db, emp, _OCT16)
    _on(monkeypatch, _OCT16)
    _report(db, emp, _OCT16)

    _on(monkeypatch, _OCT17)
    assert _pending(db, user) == []


def test_an_incomplete_today_report_is_a_warning_not_a_pending_date(
    db, employee, monkeypatch
):
    """A half-day report on a full present day trips the warn-only mismatch
    but never adds today to `pending_dates`."""
    emp, user = employee
    _attend(db, emp, _OCT16)
    report = _report(db, emp, _OCT16)
    db.add(
        WorkReportPeriod(
            report_id=report.id,
            day_part="first_half",
            period_status=DayStatus.work_at_office,
            work_fraction=0.5,
        )
    )
    db.commit()
    _on(monkeypatch, _OCT16)

    snapshot = employee_compliance(db, user)
    assert snapshot["fraction_mismatch_today"] is True
    assert snapshot["pending_dates"] == []


def test_another_employees_gaps_are_not_mine(db, employee, make_user, make_employee):
    emp, user = employee
    other_user = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="EMP802", user_id=other_user.id)
    _attend(db, other, D1)
    _attend(db, emp, D2)

    assert _pending(db, user) == [D2]
    assert _pending(db, other_user) == [D1]
