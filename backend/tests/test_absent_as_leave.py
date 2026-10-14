"""A PM-marked ABSENT day costs one leave day and stays ABSENT.

    Attendance  ABSENT  (never converted to leave)
    Auto report ABSENT  (day_status = absent, not leave, not week_off)
    Ledger      1 day   (the 1.00 leave_day_fraction attendance.service states)

Nothing but the attendance row is ever charged: the report job writes reports
only, so re-running it any number of times leaves the charge at one day.

EFFECTIVE DATE. The charge is the fraction stated on the row when a PM records
the Absent. An Absent row written before this rule states nothing, so the ledger
(NULL -> only `leave` costs 1) keeps it at 0 - historical balances do not move.

CALENDAR: Mon 17 - Fri 21 Aug 2026 are working weekdays; 22 Aug is a 4th
(non-working) Saturday.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.attendance import service as attendance_service
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.attendance.schemas import (
    AttendanceBulkRecord,
    AttendanceCreate,
    AttendanceUpdate,
)
from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.leave.models import LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import (
    auto_report_author_editable,
    generate_auto_leave_reports,
    generate_auto_reports,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportOrigin,
    WorkReportPeriod,
    WorkReportStatus,
)
from app.shared.errors import AppError

_MON = date(2026, 8, 17)
_TUE = date(2026, 8, 18)
_WED = date(2026, 8, 19)
_THU = date(2026, 8, 20)
_FRI = date(2026, 8, 21)
_SAT_OFF = date(2026, 8, 22)
_SUN = date(2026, 8, 23)
_WEEK = [_MON, _TUE, _WED, _THU, _FRI]


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="EMP001", first_name="Santosh",
                         last_name="Kumar")


@pytest.fixture()
def pm(make_user):
    return make_user("pm@example.com", role=UserRole.project_manager)


# --- helpers ---------------------------------------------------------------


def _mark(db, pm, employee, day, status=AttendanceStatus.absent):
    """The PM marking a day in Records, through the real service."""
    return attendance_service.create_attendance(
        db, pm,
        AttendanceCreate(employee_id=employee.id, attendance_date=day, status=status, note="Correction"),
    )


def _consumed(db, employee):
    return sum(
        ledger._consumed_by_month(db, employee.id, _MON, _SUN).values(),
        Decimal("0"),
    )


def _sweep(db, dates=None):
    return generate_auto_leave_reports(db, dates=dates or _WEEK)


def _reports(db, employee, day=None):
    q = db.query(DailyWorkReport).filter(DailyWorkReport.employee_id == employee.id)
    if day is not None:
        q = q.filter(DailyWorkReport.report_date == day)
    return q.all()


def _report(db, employee, day):
    rows = _reports(db, employee, day)
    assert len(rows) <= 1, rows
    return rows[0] if rows else None


def _attendance_rows(db, employee):
    return (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee.id)
        .all()
    )


# --- leave calculation -------------------------------------------------------


def test_an_absent_day_consumes_one_leave_day_and_stays_absent(db, pm, employee):
    record = _mark(db, pm, employee, _WED)

    assert record.status == AttendanceStatus.absent
    assert record.leave_day_fraction == Decimal("1.00")
    assert _consumed(db, employee) == Decimal("1")


def test_two_absent_days_consume_two(db, pm, employee):
    _mark(db, pm, employee, _TUE)
    _mark(db, pm, employee, _WED)

    assert _consumed(db, employee) == Decimal("2")


def test_a_sent_fraction_cannot_change_what_absent_costs(db, pm, employee):
    """The PM dialog sends null for every status but half_day; Absent is
    always one day whatever arrives."""
    record = attendance_service.create_attendance(
        db, pm,
        AttendanceCreate(
            employee_id=employee.id, attendance_date=_WED,
            status=AttendanceStatus.absent, leave_day_fraction=0,
            note="Correction",
        ),
    )
    assert record.leave_day_fraction == Decimal("1.00")


def test_leave_still_costs_one_and_stays_leave(db, pm, employee):
    record = _mark(db, pm, employee, _WED, AttendanceStatus.leave)

    assert record.status == AttendanceStatus.leave
    assert record.leave_day_fraction is None
    assert _consumed(db, employee) == Decimal("1")


def test_week_off_and_holiday_consume_nothing(db, employee):
    db.add(CalendarEvent(event_date=_THU, title="Festival",
                         event_type=CalendarEventType.holiday))
    db.commit()

    generate_auto_reports(db, dates=[_THU, _SAT_OFF, _SUN])

    assert _report(db, employee, _THU).day_status == DayStatus.company_holiday
    assert _report(db, employee, _SAT_OFF).day_status == DayStatus.week_off
    assert _attendance_rows(db, employee) == []
    assert _consumed(db, employee) == Decimal("0")


# --- historical records ------------------------------------------------------


def _historical_absent(db, employee, day):
    """An Absent row as it exists from before the rule: no stated charge."""
    record = AttendanceRecord(
        employee_id=employee.id, attendance_date=day,
        status=AttendanceStatus.absent, total_minutes=0, overtime_minutes=0,
    )
    db.add(record)
    db.commit()
    return record


def test_an_absent_from_before_the_rule_is_not_newly_charged(db, pm, employee):
    _historical_absent(db, employee, _MON)
    _mark(db, pm, employee, _WED)

    # Only the Absent recorded under the rule costs anything.
    assert _consumed(db, employee) == Decimal("1")


def test_resaving_a_historical_absent_does_not_charge_it(db, pm, employee):
    """The dialog re-sends status + null fraction on a note edit."""
    record = _historical_absent(db, employee, _MON)

    attendance_service.update_attendance(
        db, pm, record.id,
        AttendanceUpdate(status=AttendanceStatus.absent, note="Called in sick",
                         leave_day_fraction=None),
    )

    db.refresh(record)
    assert record.leave_day_fraction is None
    assert _consumed(db, employee) == Decimal("0")


def test_a_sheet_resave_does_not_charge_a_historical_absent(db, pm, employee):
    _historical_absent(db, employee, _MON)

    attendance_service.bulk_save_attendance(
        db, pm, _MON,
        [AttendanceBulkRecord(employee_id=employee.id,
                              status=AttendanceStatus.absent)],
        note="Correction",
    )

    assert _consumed(db, employee) == Decimal("0")


def test_the_sheet_charges_a_newly_marked_absent(db, pm, employee):
    attendance_service.bulk_save_attendance(
        db, pm, _WED,
        [AttendanceBulkRecord(employee_id=employee.id,
                              status=AttendanceStatus.absent)],
        note="Correction",
    )

    assert _consumed(db, employee) == Decimal("1")


# --- auto report -------------------------------------------------------------


def test_absent_generates_an_automatic_absent_report(db, pm, employee):
    _mark(db, pm, employee, _WED)

    result = _sweep(db)

    assert result.created == 1
    report = _report(db, employee, _WED)
    assert report.day_status == DayStatus.absent
    assert report.day_status not in (DayStatus.leave, DayStatus.week_off)
    assert report.origin == ReportOrigin.auto
    assert report.status == WorkReportStatus.submitted
    assert report.total_minutes == 0
    periods = (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report.id)
        .all()
    )
    assert [p.period_status for p in periods] == [DayStatus.absent]
    # Locked, like a leave report, while the Absent stands.
    assert auto_report_author_editable(report) is False


def test_rerunning_the_job_neither_duplicates_nor_recharges(db, pm, employee):
    _mark(db, pm, employee, _WED)

    runs = [_sweep(db).created for _ in range(5)]

    assert runs == [1, 0, 0, 0, 0]
    assert len(_reports(db, employee, _WED)) == 1
    assert len(_attendance_rows(db, employee)) == 1
    assert _consumed(db, employee) == Decimal("1")


def test_a_historical_absent_still_reports_absent(db, employee):
    """Reporting mirrors the attendance status; the charge is a separate fact."""
    _historical_absent(db, employee, _WED)

    _sweep(db)

    assert _report(db, employee, _WED).day_status == DayStatus.absent
    assert _consumed(db, employee) == Decimal("0")


def test_absent_on_a_closed_day_is_left_to_the_closed_day_sweep(db, pm, employee):
    _mark(db, pm, employee, _SAT_OFF)

    result = _sweep(db, [_SAT_OFF])

    assert result.created == 0
    assert result.non_working_dates == 1


def test_an_employees_own_report_wins_over_an_absent(db, pm, employee):
    db.add(DailyWorkReport(
        employee_id=employee.id, report_date=_WED,
        status=WorkReportStatus.submitted, origin=ReportOrigin.employee,
        report_mode="full_day", day_status=DayStatus.work_at_office,
        total_minutes=480,
    ))
    db.commit()
    _mark(db, pm, employee, _WED)

    assert _sweep(db).created == 0
    assert _report(db, employee, _WED).origin == ReportOrigin.employee


# --- attendance changes keep the report in step ---------------------------


def test_changing_absent_to_present_releases_report_and_charge(db, pm, employee):
    record = _mark(db, pm, employee, _WED)
    _sweep(db)

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.present, note="Correction")
    )

    db.refresh(record)
    assert record.leave_day_fraction is None
    assert _report(db, employee, _WED) is None
    assert _consumed(db, employee) == Decimal("0")
    assert _sweep(db).created == 0


def test_deleting_absent_releases_report_and_charge(db, pm, employee):
    record = _mark(db, pm, employee, _WED)
    _sweep(db)

    attendance_service.delete_attendance(db, pm, record.id)

    assert _report(db, employee, _WED) is None
    assert _consumed(db, employee) == Decimal("0")
    assert _sweep(db).created == 0


def test_changing_present_to_absent_charges_and_reports(db, pm, employee):
    record = _mark(db, pm, employee, _WED, AttendanceStatus.present)
    assert _consumed(db, employee) == Decimal("0")

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.absent, note="Correction")
    )

    db.refresh(record)
    assert record.leave_day_fraction == Decimal("1.00")
    assert _consumed(db, employee) == Decimal("1")
    _sweep(db)
    assert _report(db, employee, _WED).day_status == DayStatus.absent


def test_changing_absent_to_leave_swaps_the_label_and_keeps_one_charge(
    db, pm, employee
):
    record = _mark(db, pm, employee, _WED)
    _sweep(db)

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.leave, note="Correction")
    )

    # The ABSENT report no longer has an Absent behind it.
    assert _report(db, employee, _WED) is None
    db.refresh(record)
    assert record.leave_day_fraction is None
    assert _consumed(db, employee) == Decimal("1")
    _sweep(db)
    assert _report(db, employee, _WED).day_status == DayStatus.leave


def test_changing_leave_to_absent_swaps_the_label_and_keeps_one_charge(
    db, pm, employee
):
    record = _mark(db, pm, employee, _WED, AttendanceStatus.leave)
    _sweep(db)
    assert _report(db, employee, _WED).day_status == DayStatus.leave

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.absent, note="Correction")
    )

    assert _report(db, employee, _WED) is None
    assert _consumed(db, employee) == Decimal("1")
    _sweep(db)
    assert _report(db, employee, _WED).day_status == DayStatus.absent


def test_a_half_day_charge_does_not_linger_on_an_absent(db, pm, employee):
    record = attendance_service.create_attendance(
        db, pm,
        AttendanceCreate(employee_id=employee.id, attendance_date=_WED,
                         status=AttendanceStatus.half_day, leave_day_fraction=0.5, note="Correction"),
    )

    attendance_service.update_attendance(
        db, pm, record.id, AttendanceUpdate(status=AttendanceStatus.absent, note="Correction")
    )

    db.refresh(record)
    assert record.leave_day_fraction == Decimal("1.00")
    assert _consumed(db, employee) == Decimal("1")


# --- approved leave + absent: never two charges ----------------------------


def test_approved_leave_over_an_absent_day_charges_that_day_once(
    db, pm, employee, make_leave_request
):
    """Existing rule: approval skips a day that already carries an attendance
    decision. So the Absent row is the day's only charge, and its report stays
    ABSENT."""
    from app.modules.leave.effects import apply_leave_approved

    _mark(db, pm, employee, _TUE)
    req = make_leave_request(
        employee_id=employee.id, start_date=_MON, end_date=_WED,
        status=LeaveStatus.approved,
    )
    effect = apply_leave_approved(db, pm, req)
    db.commit()

    assert effect.skipped == [_TUE]
    assert len(_attendance_rows(db, employee)) == 3
    assert _consumed(db, employee) == Decimal("3")

    for _ in range(3):
        _sweep(db, [_MON, _TUE, _WED])
    assert _report(db, employee, _MON).day_status == DayStatus.leave
    assert _report(db, employee, _TUE).day_status == DayStatus.absent
    assert _report(db, employee, _WED).day_status == DayStatus.leave
    assert _consumed(db, employee) == Decimal("3")


# --- nobody chooses Absent on their own report -----------------------------


def test_an_employee_cannot_declare_absent_on_a_report():
    from app.modules.work_reports.service import _normalize_periods

    with pytest.raises(AppError) as err:
        _normalize_periods(None, None, day_status=DayStatus.absent,
                           location=None, tasks=[])
    assert err.value.status_code == 422
