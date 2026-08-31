"""Phase 3E - automatic LEAVE Daily Work Reports.

Covers the whole of the phase: which leave states generate, which dates of a
leave range receive a report (the calendar decides, via the leave module's own
day resolution), the fields the report is created with, the employee population,
"an existing report always wins", idempotency, and the two guarantees this phase
must not break - that the week-off sweep and the leave sweep never claim the same
date, and that Phase 3D reconciliation cannot see a leave report.

CALENDAR ANCHORS
================
The office week is Mon-Fri plus the 1st/3rd/5th Saturday; only the 2nd and 4th
Saturday are off (`calendar.working_days`). August 2026 starts on a Saturday, so
its Saturdays fall 1st/2nd/3rd/4th/5th on the 1st/8th/15th/22nd/29th - which
makes 22 Aug a genuinely non-working Saturday and 15 Aug a working one. Every
constant below is pinned by `test_calendar_anchors...` so a test cannot pass for
the wrong reason.
"""
from datetime import date

import pytest

from app.modules.leave.models import LeaveStatus, LeaveType
from app.modules.work_reports.auto_reports import (
    AUTO_LEAVE_DAY_STATUS,
    AUTO_LEAVE_STATUSES,
    AUTO_WEEKEND_DAY_STATUS,
    approved_leave_days,
    ensure_auto_report,
    generate_auto_leave_reports,
    generate_auto_reports,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportStatus,
)

# Mon 17 -> Fri 21 Aug 2026: five ordinary working weekdays.
_MON = date(2026, 8, 17)
_TUE = date(2026, 8, 18)
_WED = date(2026, 8, 19)
_THU = date(2026, 8, 20)
_FRI = date(2026, 8, 21)
_WEEK = [_MON, _TUE, _WED, _THU, _FRI]
# The weekend after it: the 4th Saturday (off) and its Sunday.
_SAT_OFF = date(2026, 8, 22)
_SUN = date(2026, 8, 23)
_MON_AFTER = date(2026, 8, 24)
# The 3rd Saturday - a WORKING Saturday with no calendar entry involved.
_SAT_WORKING = date(2026, 8, 15)


def test_calendar_anchors_are_the_days_these_tests_assume():
    from app.modules.calendar.working_days import saturday_occurrence

    assert [d.weekday() for d in _WEEK] == [0, 1, 2, 3, 4]
    assert _SAT_OFF.weekday() == 5 and saturday_occurrence(_SAT_OFF) == 4
    assert _SAT_WORKING.weekday() == 5 and saturday_occurrence(_SAT_WORKING) == 3
    assert _SUN.weekday() == 6
    assert _MON_AFTER.weekday() == 0


# --- helpers ---------------------------------------------------------------


def _calendar_event(db, *, event_date, event_type, title="Test"):
    from app.modules.calendar.models import CalendarEvent, CalendarEventType

    ev = CalendarEvent(
        event_date=event_date, title=title, event_type=CalendarEventType(event_type)
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _reports_for(db, employee_id, report_date=None):
    q = db.query(DailyWorkReport).filter(DailyWorkReport.employee_id == employee_id)
    if report_date is not None:
        q = q.filter(DailyWorkReport.report_date == report_date)
    return q.all()


def _dates_of(db, employee_id):
    return sorted(r.report_date for r in _reports_for(db, employee_id))


def _run(db, dates):
    return generate_auto_leave_reports(db, dates=dates)


@pytest.fixture()
def employee(make_employee):
    return make_employee(
        employee_code="EMP001", first_name="Santosh", last_name="Kumar"
    )


@pytest.fixture()
def approved_week(make_leave_request, employee):
    """Approved leave over the whole of Mon 17 - Fri 21 Aug 2026."""
    return make_leave_request(
        employee_id=employee.id,
        start_date=_MON,
        end_date=_FRI,
        status=LeaveStatus.approved,
    )


# --- 1. the happy path ------------------------------------------------------


def test_approved_leave_creates_one_auto_report_per_working_day(
    db, employee, approved_week
):
    result = _run(db, _WEEK)

    assert result.created == 5
    assert _dates_of(db, employee.id) == _WEEK


def test_the_generated_leave_report_has_the_phase_3e_shape(
    db, employee, approved_week
):
    _run(db, [_WED])

    report = _reports_for(db, employee.id, _WED)[0]
    assert report.origin == ReportOrigin.auto
    assert report.day_status == DayStatus.leave
    # Born SUBMITTED: an approved absence accounts for the day.
    assert report.status == WorkReportStatus.submitted
    assert report.report_mode == ReportMode.full_day.value
    assert report.total_minutes == 0
    # `status == submitted AND submitted_at IS NULL` is a combination no other
    # code path produces, so the two are kept moving together.
    assert report.submitted_at is not None
    # Nobody authored it; `origin` is the indicator, this is the consequence.
    assert report.created_by is None
    assert report.updated_by is None
    # Submission side effects that belong to a person, not to this generator.
    assert report.reviewed_by is None
    assert report.reviewed_at is None
    assert report.review_note is None
    assert report.remarks is None


def test_the_leave_report_gets_a_full_day_period_like_a_typed_one(
    db, employee, approved_week
):
    from decimal import Decimal

    from app.modules.work_reports.models import DayPart, WorkReportPeriod

    _run(db, [_WED])
    report = _reports_for(db, employee.id, _WED)[0]

    periods = (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report.id)
        .all()
    )
    assert len(periods) == 1
    period = periods[0]
    assert period.day_part == DayPart.full_day.value
    assert period.period_status == DayStatus.leave
    assert period.work_fraction == Decimal("1.0")
    assert period.is_legacy_half_day is False


def test_the_leave_report_carries_no_task_lines(db, employee, approved_week):
    from app.modules.work_reports.models import WorkReportTask

    _run(db, [_WED])
    report = _reports_for(db, employee.id, _WED)[0]

    assert (
        db.query(WorkReportTask)
        .filter(WorkReportTask.report_id == report.id)
        .count()
        == 0
    )


# --- 2. only `approved` generates -------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        LeaveStatus.pending,
        LeaveStatus.rejected,
        LeaveStatus.cancelled,
        LeaveStatus.cancellation_requested,
    ],
)
def test_leave_that_is_not_approved_generates_nothing(
    db, employee, make_leave_request, status
):
    make_leave_request(
        employee_id=employee.id, start_date=_MON, end_date=_FRI, status=status
    )

    result = _run(db, _WEEK)

    assert result.created == 0
    assert result.employees_considered == 0
    assert _reports_for(db, employee.id) == []


def test_cancellation_requested_is_excluded_deliberately_not_by_omission(db):
    """A DIVERGENCE from the two modules that DO treat `cancellation_requested`
    as live leave, pinned here so nobody "fixes" it by accident.

    `leave_balances.ledger` and the daily report reminder both count it, and are
    right to - the absence stands until a manager rules on the withdrawal. But
    both of those READ a day; this phase WRITES a row, and it owns no way to take
    one back. So a leave under withdrawal gets no automatic report, and the
    employee's day stays open to them.
    """
    from app.modules.leave_balances.ledger import LIVE_LEAVE_STATUSES
    from app.reminders.daily_report.service import _ACTIVE_LEAVE_STATUSES

    assert LeaveStatus.cancellation_requested in LIVE_LEAVE_STATUSES
    assert LeaveStatus.cancellation_requested in _ACTIVE_LEAVE_STATUSES
    assert tuple(AUTO_LEAVE_STATUSES) == (LeaveStatus.approved,)


def test_an_already_generated_report_is_not_withdrawn_when_cancellation_is_asked(
    db, employee, approved_week
):
    """No leave reconciliation in this phase, stated as a test: the row written
    while the leave was approved stands, and the sweep simply stops adding new
    ones."""
    assert _run(db, [_MON, _TUE]).created == 2
    approved_week.status = LeaveStatus.cancellation_requested
    db.commit()

    later = _run(db, _WEEK)

    assert later.created == 0
    # Mon/Tue keep the reports they already had; Wed-Fri never get one.
    assert _dates_of(db, employee.id) == [_MON, _TUE]


# --- 3. which dates: the calendar decides -----------------------------------


def test_a_company_holiday_inside_the_range_gets_no_leave_report(
    db, employee, approved_week
):
    """The example from the spec: Mon-Fri leave with Wednesday a company
    holiday. Wednesday is not a working day, so it is not a day the absence cost
    anything, and it gets no leave report."""
    _calendar_event(db, event_date=_WED, event_type="holiday", title="Holiday")

    result = _run(db, _WEEK)

    assert result.created == 4
    assert _dates_of(db, employee.id) == [_MON, _TUE, _THU, _FRI]
    assert _reports_for(db, employee.id, _WED) == []


def test_the_weekend_inside_a_leave_range_gets_no_leave_report(
    db, employee, make_leave_request
):
    """Fri -> Mon leave is two days, not four: the 4th Saturday and the Sunday
    between them are closed."""
    make_leave_request(
        employee_id=employee.id,
        start_date=_FRI,
        end_date=_MON_AFTER,
        status=LeaveStatus.approved,
    )

    result = _run(db, [_FRI, _SAT_OFF, _SUN, _MON_AFTER])

    assert result.created == 2
    assert result.non_working_dates == 2
    assert _dates_of(db, employee.id) == [_FRI, _MON_AFTER]


def test_a_working_saturday_inside_a_leave_range_does_get_one(
    db, employee, make_leave_request
):
    """The 3rd Saturday works by the baseline office week, with no calendar entry
    involved - so an absence on it is a real absence."""
    make_leave_request(
        employee_id=employee.id,
        start_date=_SAT_WORKING,
        end_date=_SAT_WORKING,
        status=LeaveStatus.approved,
    )

    assert _run(db, [_SAT_WORKING]).created == 1
    assert _reports_for(db, employee.id, _SAT_WORKING)[0].day_status == DayStatus.leave


def test_a_working_day_override_turns_a_closed_saturday_into_a_leave_day(
    db, employee, make_leave_request
):
    """The override read from the OTHER side. A declared `working_day` beats the
    weekend rule, so the office was open and the absence counts - the same single
    rule that suppresses the week-off report for that date."""
    _calendar_event(db, event_date=_SAT_OFF, event_type="working_day")
    make_leave_request(
        employee_id=employee.id,
        start_date=_SAT_OFF,
        end_date=_SAT_OFF,
        status=LeaveStatus.approved,
    )

    assert _run(db, [_SAT_OFF]).created == 1
    assert _reports_for(db, employee.id, _SAT_OFF)[0].day_status == DayStatus.leave


def test_leave_entirely_on_closed_days_generates_nothing(
    db, employee, make_leave_request
):
    make_leave_request(
        employee_id=employee.id,
        start_date=_SAT_OFF,
        end_date=_SUN,
        status=LeaveStatus.approved,
    )

    result = _run(db, [_SAT_OFF, _SUN])

    assert result.created == 0
    assert _reports_for(db, employee.id) == []


def test_the_generated_dates_are_exactly_the_leave_modules_own_working_days(
    db, employee, approved_week
):
    """The anti-duplication guarantee: this sweep may not have its own opinion
    about which days a leave covers. Whatever `leave.effects.leave_working_days`
    says - the same function `apply_leave_approved` marked attendance from - is
    what gets a report."""
    from app.modules.leave.effects import leave_working_days

    _calendar_event(db, event_date=_THU, event_type="cdc_holiday")

    _run(db, _WEEK)

    assert _dates_of(db, employee.id) == leave_working_days(db, _MON, _FRI)


# --- 4. an existing report always wins --------------------------------------


def _employee_report(db, employee_id, report_date, **kwargs):
    fields = dict(
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        total_minutes=480,
    )
    fields.update(kwargs)
    report = DailyWorkReport(
        employee_id=employee_id, report_date=report_date, **fields
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_an_existing_employee_report_on_a_leave_day_is_preserved_untouched(
    db, employee, approved_week
):
    existing = _employee_report(
        db, employee.id, _WED, remarks="Came in for the review call"
    )
    existing_id = existing.id

    result = _run(db, _WEEK)

    assert result.created == 4
    assert result.skipped_existing == 1
    reports = _reports_for(db, employee.id, _WED)
    assert len(reports) == 1
    kept = reports[0]
    assert kept.id == existing_id
    # Not overwritten, not restamped, not relabelled, not deleted.
    assert kept.origin == ReportOrigin.employee
    assert kept.day_status == DayStatus.work_at_office
    assert kept.total_minutes == 480
    assert kept.remarks == "Came in for the review call"


def test_an_existing_draft_also_blocks_leave_generation(db, employee, approved_week):
    _employee_report(
        db,
        employee.id,
        _WED,
        status=WorkReportStatus.draft,
        day_status=DayStatus.comp_off,
        total_minutes=0,
    )

    assert _run(db, [_WED]).created == 0
    reports = _reports_for(db, employee.id, _WED)
    assert len(reports) == 1
    assert reports[0].origin == ReportOrigin.employee
    assert reports[0].day_status == DayStatus.comp_off


# --- 5. idempotency ---------------------------------------------------------


def test_running_the_leave_sweep_twice_creates_no_duplicates(
    db, employee, approved_week
):
    first = _run(db, _WEEK)
    assert first.created == 5
    total = db.query(DailyWorkReport).count()
    assert total == 5

    second = _run(db, _WEEK)
    third = _run(db, _WEEK)

    assert second.created == 0
    assert second.skipped_existing == 5
    assert third.created == 0
    assert db.query(DailyWorkReport).count() == total
    for day in _WEEK:
        assert len(_reports_for(db, employee.id, day)) == 1


def test_the_scheduled_window_sweep_is_idempotent(db, employee, approved_week):
    """The real job sweeps `[today - lookback, today]`, which spans working and
    closed days and dates outside the leave at once."""
    first = generate_auto_leave_reports(db, today=_FRI, lookback_days=7)
    second = generate_auto_leave_reports(db, today=_FRI, lookback_days=7)

    assert second.created == 0
    # 14-21 Aug swept. Working: Fri 14, Sat 15 (3rd), Mon 17 - Fri 21. The leave
    # covers Mon 17 - Fri 21, so five.
    assert first.created == 5
    assert _dates_of(db, employee.id) == _WEEK


def test_the_window_never_reaches_a_future_leave_day(
    db, employee, make_leave_request
):
    """The window ends at `today`, so leave approved for later is filed on each
    of its own mornings - which is what keeps this phase free of any obligation
    to unwrite a report when a leave is later withdrawn."""
    make_leave_request(
        employee_id=employee.id,
        start_date=_MON,
        end_date=_FRI,
        status=LeaveStatus.approved,
    )

    result = generate_auto_leave_reports(db, today=_TUE, lookback_days=7)

    assert result.created == 2
    assert _dates_of(db, employee.id) == [_MON, _TUE]


# --- 6. the employee population ---------------------------------------------


def test_only_the_employee_on_leave_gets_a_report(db, make_employee,
                                                  make_leave_request):
    on_leave = make_employee(employee_code="EMP-LEAVE")
    at_work = make_employee(employee_code="EMP-WORK")
    make_leave_request(
        employee_id=on_leave.id,
        start_date=_WED,
        end_date=_WED,
        status=LeaveStatus.approved,
    )

    result = _run(db, _WEEK)

    assert result.created == 1
    assert result.employees_considered == 1
    assert _dates_of(db, on_leave.id) == [_WED]
    assert _reports_for(db, at_work.id) == []


def test_two_employees_on_leave_on_the_same_day_each_get_one(
    db, make_employee, make_leave_request
):
    a = make_employee(employee_code="EMP-A")
    b = make_employee(employee_code="EMP-B")
    for emp in (a, b):
        make_leave_request(
            employee_id=emp.id,
            start_date=_WED,
            end_date=_THU,
            status=LeaveStatus.approved,
        )

    result = _run(db, _WEEK)

    assert result.created == 4
    assert _dates_of(db, a.id) == [_WED, _THU]
    assert _dates_of(db, b.id) == [_WED, _THU]


def test_project_manager_logins_are_not_given_leave_reports(
    db, make_user, make_employee, make_leave_request
):
    """The same population `report_submitters` gives the week-off sweep: a PM
    login does not file daily reports, so there is nothing to file for them."""
    from app.modules.users.models import UserRole

    pm_user = make_user("pm@example.com", role=UserRole.project_manager)
    pm_emp = make_employee(employee_code="EMP-PM", user_id=pm_user.id)
    make_leave_request(
        employee_id=pm_emp.id,
        start_date=_WED,
        end_date=_WED,
        status=LeaveStatus.approved,
    )

    result = _run(db, [_WED])

    assert result.created == 0
    assert result.employees_considered == 0
    assert _reports_for(db, pm_emp.id) == []


def test_non_active_and_deleted_employees_are_skipped(db, make_employee,
                                                      make_leave_request):
    from datetime import datetime, timezone

    from app.modules.employees.models import EmployeeStatus

    exited = make_employee(employee_code="EMP-EXITED", status=EmployeeStatus.exited)
    deleted = make_employee(employee_code="EMP-DELETED")
    deleted.deleted_at = datetime.now(timezone.utc)
    db.commit()
    active = make_employee(employee_code="EMP-ACTIVE")
    for emp in (exited, deleted, active):
        make_leave_request(
            employee_id=emp.id,
            start_date=_WED,
            end_date=_WED,
            status=LeaveStatus.approved,
        )

    result = _run(db, [_WED])

    assert result.created == 1
    assert _reports_for(db, exited.id) == []
    assert _reports_for(db, deleted.id) == []
    assert len(_reports_for(db, active.id, _WED)) == 1


def test_a_day_before_the_employee_joined_is_never_generated(
    db, make_employee, make_leave_request
):
    joiner = make_employee(employee_code="EMP-NEW")
    joiner.date_of_joining = _THU
    db.commit()
    make_leave_request(
        employee_id=joiner.id,
        start_date=_MON,
        end_date=_FRI,
        status=LeaveStatus.approved,
    )

    result = _run(db, _WEEK)

    assert result.created == 2
    assert _dates_of(db, joiner.id) == [_THU, _FRI]


def test_no_leave_at_all_is_not_an_error(db, employee):
    result = _run(db, _WEEK)

    assert result.created == 0
    assert result.employees_considered == 0
    assert db.query(DailyWorkReport).count() == 0


# --- 7. approved_leave_days, the date inversion -----------------------------


def test_approved_leave_days_maps_only_working_days_in_the_window(
    db, employee, make_leave_request
):
    """A leave that starts before the window and ends after it still contributes
    the window's own working days, and nothing outside them."""
    make_leave_request(
        employee_id=employee.id,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        status=LeaveStatus.approved,
    )

    mapping = approved_leave_days(db, [_FRI, _SAT_OFF, _SUN, _MON_AFTER])

    assert sorted(mapping) == [_FRI, _MON_AFTER]
    assert mapping[_FRI] == {employee.id}


def test_approved_leave_days_is_empty_for_no_dates(db, employee, approved_week):
    assert approved_leave_days(db, []) == {}


# --- 8. the two sweeps never claim the same date ----------------------------


def test_the_week_off_and_leave_sweeps_do_not_collide(db, employee, make_leave_request):
    """Run BOTH over a window spanning a leave, a weekend and ordinary working
    days. Every date ends with at most one report, and the day_status is decided
    by the one calendar rule read from its two sides."""
    make_leave_request(
        employee_id=employee.id,
        start_date=_THU,
        end_date=_MON_AFTER,
        status=LeaveStatus.approved,
    )
    window = [_THU, _FRI, _SAT_OFF, _SUN, _MON_AFTER]

    weekend = generate_auto_reports(db, dates=window)
    leave = generate_auto_leave_reports(db, dates=window)

    assert weekend.created == 2  # Sat 22 + Sun 23
    assert leave.created == 3  # Thu 20, Fri 21, Mon 24
    by_date = {r.report_date: r for r in _reports_for(db, employee.id)}
    assert sorted(by_date) == window
    assert by_date[_THU].day_status == DayStatus.leave
    assert by_date[_FRI].day_status == DayStatus.leave
    assert by_date[_SAT_OFF].day_status == DayStatus.week_off
    assert by_date[_SUN].day_status == DayStatus.week_off
    assert by_date[_MON_AFTER].day_status == DayStatus.leave


def test_running_the_sweeps_in_the_other_order_gives_the_same_result(
    db, employee, make_leave_request
):
    make_leave_request(
        employee_id=employee.id,
        start_date=_THU,
        end_date=_MON_AFTER,
        status=LeaveStatus.approved,
    )
    window = [_THU, _FRI, _SAT_OFF, _SUN, _MON_AFTER]

    generate_auto_leave_reports(db, dates=window)
    generate_auto_reports(db, dates=window)

    statuses = {
        r.report_date: r.day_status for r in _reports_for(db, employee.id)
    }
    assert statuses == {
        _THU: DayStatus.leave,
        _FRI: DayStatus.leave,
        _SAT_OFF: DayStatus.week_off,
        _SUN: DayStatus.week_off,
        _MON_AFTER: DayStatus.leave,
    }


def test_ensure_auto_report_refuses_the_wrong_side_of_the_calendar(db, employee):
    """The writer's own gate, standing alone with no override sets given, so it
    reads the calendar for the one date itself."""
    on_closed_day = ensure_auto_report(
        db, employee, _SUN, day_status=DayStatus.leave, on_working_day=True
    )
    assert on_closed_day.reason == "non_working_day"
    assert on_closed_day.created is False

    on_open_day = ensure_auto_report(db, employee, _WED)
    assert on_open_day.reason == "working_day"
    assert on_open_day.created is False

    assert _reports_for(db, employee.id) == []


# --- 9. Phase 3D reconciliation cannot see a leave report -------------------


def test_calendar_reconciliation_never_touches_an_auto_leave_report(
    db, employee, approved_week
):
    """Reconciliation is scoped to `origin = auto AND day_status = week_off`. A
    leave report carries a different day_status and is therefore outside every
    query it runs - including when the date it sits on is itself re-declared."""
    from app.modules.work_reports.auto_reports import (
        reconcile_auto_reports_for_calendar_change,
    )

    _run(db, [_WED])
    generated = _reports_for(db, employee.id, _WED)[0]
    generated_id = generated.id

    result = reconcile_auto_reports_for_calendar_change(db, [_WED])

    assert result.examined == 0
    assert result.deleted == 0
    assert result.reclassified == 0
    survivor = _reports_for(db, employee.id, _WED)[0]
    assert survivor.id == generated_id
    assert survivor.day_status == DayStatus.leave
    assert survivor.status == WorkReportStatus.submitted


def test_the_reconciliation_query_does_not_match_a_leave_report(
    db, employee, approved_week
):
    _run(db, _WEEK)

    stale = (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.origin == ReportOrigin.auto,
            DailyWorkReport.day_status == AUTO_WEEKEND_DAY_STATUS,
            DailyWorkReport.report_date.in_(_WEEK),
        )
        .all()
    )
    assert stale == []


# --- 10. the pre-existing lock becomes reachable ----------------------------


def test_a_generated_leave_report_is_not_author_editable(db, make_user,
                                                         make_employee,
                                                         make_leave_request):
    """Not new behaviour and not changed by this phase: Phase 3C wrote
    `AUTO_LOCKED_DAY_STATUSES = {leave}` as the default-deny half of
    `auto_report_author_editable`, when nothing generated such a row. Generating
    one is what makes the rule live, so it is pinned against a REAL generated
    report rather than a hand-built one."""
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.auto_reports import auto_report_author_editable

    user = make_user("author@example.com")
    emp = make_employee(employee_code="EMP-AUTHOR", user_id=user.id)
    make_leave_request(
        employee_id=emp.id,
        start_date=_WED,
        end_date=_WED,
        status=LeaveStatus.approved,
    )
    _run(db, [_WED])
    report = _reports_for(db, emp.id, _WED)[0]

    assert report.day_status == AUTO_LEAVE_DAY_STATUS
    assert auto_report_author_editable(report) is False
    assert svc.get_work_report(db, user, report.id).can_self_edit is False


# --- 11. leave type is irrelevant to generation -----------------------------


@pytest.mark.parametrize("leave_type", list(LeaveType))
def test_every_leave_type_generates_the_same_report(
    db, employee, make_leave_request, leave_type
):
    """Whether the pool pays for the absence (`effects.BALANCE_DEDUCTING_TYPES`)
    is a balance question. Unpaid leave is still absence, so it still accounts
    for the day."""
    make_leave_request(
        employee_id=employee.id,
        start_date=_WED,
        end_date=_WED,
        leave_type=leave_type,
        status=LeaveStatus.approved,
    )

    assert _run(db, [_WED]).created == 1
    assert _reports_for(db, employee.id, _WED)[0].day_status == DayStatus.leave
