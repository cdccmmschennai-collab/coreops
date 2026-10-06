"""Automatic HOLIDAY reports - a calendar-closed day is labelled
`company_holiday`, a weekly off stays `week_off`.

The closed-day sweep (`generate_auto_reports`) used to label every closed date
`week_off`. A date a calendar entry closes (holiday / cdc_holiday /
natural_hazard) now gets `company_holiday`; a date closed only by the weekly rule
(Sunday, 2nd/4th Saturday) keeps `week_off`. A holiday on a weekly off is a
holiday - the declared entry outranks the weekly rule, as `is_working_day` and
the attendance calendar already rank them.

CALENDAR ANCHORS
================
August 2026 starts on a Saturday: 22 Aug is the 4th Saturday (off), 23 Aug a
Sunday, 17-21 Aug an ordinary Mon-Fri week.
"""
from datetime import date

import pytest

from app.modules.attendance.models import AttendanceRecord
from app.modules.calendar import service as calendar_service
from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.schemas import CalendarEventCreate
from app.modules.leave.models import LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import (
    AUTO_HOLIDAY_DAY_STATUS,
    AUTO_WEEKEND_DAY_STATUS,
    ensure_auto_report,
    generate_auto_leave_reports,
    generate_auto_reports,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportPeriod,
    WorkReportStatus,
)

_MON = date(2026, 8, 17)
_TUE = date(2026, 8, 18)
_WED = date(2026, 8, 19)
_THU = date(2026, 8, 20)
_FRI = date(2026, 8, 21)
_SAT_OFF = date(2026, 8, 22)
_SUN = date(2026, 8, 23)


def test_calendar_anchors_are_the_days_these_tests_assume():
    from app.modules.calendar.working_days import saturday_occurrence

    assert [d.weekday() for d in (_MON, _TUE, _WED, _THU, _FRI)] == [0, 1, 2, 3, 4]
    assert _SAT_OFF.weekday() == 5 and saturday_occurrence(_SAT_OFF) == 4
    assert _SUN.weekday() == 6


def test_the_holiday_status_is_the_existing_company_holiday_value():
    # No parallel status system: the label is the taxonomy's own member.
    assert AUTO_HOLIDAY_DAY_STATUS is DayStatus.company_holiday
    assert AUTO_WEEKEND_DAY_STATUS is DayStatus.week_off


# --- helpers ---------------------------------------------------------------


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="EMP001", first_name="Santosh",
                         last_name="Kumar")


@pytest.fixture()
def pm(make_user):
    return make_user("pm@example.com", role=UserRole.project_manager)


def _calendar_event(db, *, event_date, event_type, title="Holiday"):
    ev = CalendarEvent(
        event_date=event_date, title=title, event_type=CalendarEventType(event_type)
    )
    db.add(ev)
    db.commit()
    return ev


def _reports_for(db, employee_id, report_date=None):
    q = db.query(DailyWorkReport).filter(DailyWorkReport.employee_id == employee_id)
    if report_date is not None:
        q = q.filter(DailyWorkReport.report_date == report_date)
    return q.all()


def _status_on(db, employee_id, report_date):
    reports = _reports_for(db, employee_id, report_date)
    assert len(reports) == 1, reports
    return reports[0].day_status


# --- 1-4. classification ----------------------------------------------------


def test_a_normal_working_day_gets_no_automatic_report(db, employee):
    result = generate_auto_reports(db, dates=[_WED])

    assert result.created == 0
    assert result.working_dates == 1
    assert _reports_for(db, employee.id) == []


def test_a_weekly_off_stays_week_off(db, employee):
    generate_auto_reports(db, dates=[_SAT_OFF, _SUN])

    assert _status_on(db, employee.id, _SAT_OFF) == DayStatus.week_off
    assert _status_on(db, employee.id, _SUN) == DayStatus.week_off


def test_a_weekday_holiday_generates_company_holiday_not_week_off(db, employee):
    _calendar_event(db, event_date=_WED, event_type="holiday")

    result = generate_auto_reports(db, dates=[_WED])

    assert result.created == 1
    report = _reports_for(db, employee.id, _WED)[0]
    assert report.day_status == DayStatus.company_holiday
    assert report.day_status != DayStatus.week_off
    # Same generated shape as every other automatic report.
    assert report.origin == ReportOrigin.auto
    assert report.status == WorkReportStatus.submitted
    assert report.submitted_at is not None
    assert report.report_mode == ReportMode.full_day.value
    assert report.total_minutes == 0
    periods = (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report.id)
        .all()
    )
    assert [p.period_status for p in periods] == [DayStatus.company_holiday]


@pytest.mark.parametrize("event_type", ["holiday", "cdc_holiday", "natural_hazard"])
def test_every_office_closing_entry_is_a_holiday(db, employee, event_type):
    """The attendance calendar resolves all three to its one `holiday` status;
    the report label follows the same rule rather than inventing a second."""
    _calendar_event(db, event_date=_THU, event_type=event_type)

    generate_auto_reports(db, dates=[_THU])

    assert _status_on(db, employee.id, _THU) == DayStatus.company_holiday


def test_a_holiday_on_a_weekly_off_is_a_holiday(db, employee):
    """The declared entry outranks the weekly rule - the precedence
    `is_working_day` already applies."""
    _calendar_event(db, event_date=_SUN, event_type="holiday")

    generate_auto_reports(db, dates=[_SAT_OFF, _SUN])

    assert _status_on(db, employee.id, _SAT_OFF) == DayStatus.week_off
    assert _status_on(db, employee.id, _SUN) == DayStatus.company_holiday


def test_a_working_day_override_beats_a_holiday(db, employee):
    _calendar_event(db, event_date=_WED, event_type="holiday")
    _calendar_event(db, event_date=_WED, event_type="working_day", title="Open")

    assert generate_auto_reports(db, dates=[_WED]).created == 0
    assert _reports_for(db, employee.id) == []


def test_ensure_auto_report_derives_the_label_on_its_own(db, employee):
    """The single writer, called standalone, reads the calendar itself."""
    _calendar_event(db, event_date=_TUE, event_type="holiday")

    assert ensure_auto_report(db, employee, _TUE).created
    assert ensure_auto_report(db, employee, _SAT_OFF).created
    assert _status_on(db, employee.id, _TUE) == DayStatus.company_holiday
    assert _status_on(db, employee.id, _SAT_OFF) == DayStatus.week_off


# --- 5. no leave ------------------------------------------------------------


def test_a_holiday_consumes_no_leave(db, employee):
    """Leave is consumed only by `attendance_records` rows, priced by the
    ledger. Generating a holiday report writes none."""
    _calendar_event(db, event_date=_WED, event_type="holiday")

    generate_auto_reports(db, dates=[_WED])
    generate_auto_leave_reports(db, dates=[_WED])

    assert (
        db.query(AttendanceRecord)
        .filter(AttendanceRecord.employee_id == employee.id)
        .count()
        == 0
    )
    assert ledger._consumed_by_month(db, employee.id, _MON, _SUN) == {}


def test_approved_leave_over_a_holiday_charges_and_reports_only_working_days(
    db, employee, pm, make_leave_request
):
    """Leave Mon-Fri with a Wednesday holiday: Wednesday is a holiday report,
    the four working days are leave reports, and the holiday is not charged."""
    from app.modules.leave.effects import apply_leave_approved

    _calendar_event(db, event_date=_WED, event_type="holiday")
    req = make_leave_request(
        employee_id=employee.id, start_date=_MON, end_date=_FRI,
        status=LeaveStatus.approved,
    )
    apply_leave_approved(db, pm, req)
    db.commit()

    week = [_MON, _TUE, _WED, _THU, _FRI]
    generate_auto_reports(db, dates=week)
    generate_auto_leave_reports(db, dates=week)

    assert _status_on(db, employee.id, _WED) == DayStatus.company_holiday
    for day in (_MON, _TUE, _THU, _FRI):
        assert _status_on(db, employee.id, day) == DayStatus.leave
    consumed = ledger._consumed_by_month(db, employee.id, _MON, _FRI)
    assert sum(consumed.values()) == 4


# --- 6. idempotency + existing reports --------------------------------------


def test_rerunning_does_not_duplicate_the_holiday_report(db, employee):
    _calendar_event(db, event_date=_WED, event_type="holiday")

    first = generate_auto_reports(db, dates=[_WED])
    second = generate_auto_reports(db, dates=[_WED])
    third = generate_auto_reports(db, dates=[_WED])

    assert (first.created, second.created, third.created) == (1, 0, 0)
    assert second.skipped_existing == 1
    assert len(_reports_for(db, employee.id, _WED)) == 1


def test_an_employees_own_report_on_a_holiday_is_untouched(db, employee):
    _calendar_event(db, event_date=_WED, event_type="holiday")
    typed = DailyWorkReport(
        employee_id=employee.id,
        report_date=_WED,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        total_minutes=480,
    )
    db.add(typed)
    db.commit()

    assert generate_auto_reports(db, dates=[_WED]).created == 0
    kept = _reports_for(db, employee.id, _WED)[0]
    assert kept.id == typed.id
    assert kept.day_status == DayStatus.work_at_office


def test_a_pre_existing_week_off_auto_report_on_a_holiday_is_not_rewritten(
    db, employee
):
    """Historical rows keep the label they were born with."""
    assert ensure_auto_report(
        db, employee, _SAT_OFF, day_status=DayStatus.week_off
    ).created
    _calendar_event(db, event_date=_SAT_OFF, event_type="holiday")

    assert generate_auto_reports(db, dates=[_SAT_OFF]).created == 0
    assert _status_on(db, employee.id, _SAT_OFF) == DayStatus.week_off


# --- calendar reconciliation sees the holiday label ------------------------


def test_deleting_the_holiday_removes_its_untouched_holiday_report(db, employee, pm):
    holiday = calendar_service.create_event(
        db, pm,
        CalendarEventCreate(event_date=_WED, title="Festival", event_type="holiday"),
    )
    generate_auto_reports(db, dates=[_WED])
    assert _status_on(db, employee.id, _WED) == DayStatus.company_holiday

    calendar_service.delete_event(db, pm, holiday.id)

    assert _reports_for(db, employee.id, _WED) == []


def test_deleting_the_holiday_preserves_a_touched_holiday_report(db, employee, pm):
    holiday = calendar_service.create_event(
        db, pm,
        CalendarEventCreate(event_date=_WED, title="Festival", event_type="holiday"),
    )
    generate_auto_reports(db, dates=[_WED])
    report = _reports_for(db, employee.id, _WED)[0]
    report.remarks = "Came in anyway"
    db.commit()

    calendar_service.delete_event(db, pm, holiday.id)

    kept = _reports_for(db, employee.id, _WED)[0]
    assert kept.id == report.id
    assert kept.remarks == "Came in anyway"
    assert kept.day_status is None
    assert kept.status == WorkReportStatus.draft
    assert kept.origin == ReportOrigin.auto
