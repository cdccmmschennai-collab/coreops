"""Phase 3C - automatic week-off Daily Work Reports.

Covers the whole of the phase: the calendar decision (including the
`working_day` override that must suppress generation), the fields an automatic
report is created with, the "an existing report always wins" rule, idempotency
across repeated runs, the employee population, and the future-reconciliation
guarantee that a stale AUTO report stays identifiable.

CALENDAR ANCHORS
================
The office week is Mon-Fri plus the 1st/3rd/5th Saturday; only the 2nd and 4th
Saturday are off (`calendar.working_days`). August 2026 starts on a Saturday, so
its Saturdays fall 1st/2nd/3rd/4th/5th on the 1st/8th/15th/22nd/29th - which
makes 22 Aug a genuinely non-working Saturday and 15 Aug a working one. Picking
the wrong Saturday here would make the "normal weekend" tests pass for the wrong
reason, so `test_calendar_anchors...` pins every constant.
"""
from datetime import date

import pytest

from app.modules.work_reports.auto_reports import (
    AUTO_WEEKEND_DAY_STATUS,
    ensure_auto_report,
    generate_auto_reports,
    report_submitters,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkReportStatus,
)

# 4th Saturday of Aug 2026 -> off by the baseline office week.
_SAT_OFF = date(2026, 8, 22)
_SUN = date(2026, 8, 23)
# 3rd Saturday -> a WORKING Saturday with no override at all.
_SAT_WORKING = date(2026, 8, 15)
# An ordinary Thursday.
_WEEKDAY = date(2026, 8, 20)


def test_calendar_anchors_are_the_days_these_tests_assume():
    from app.modules.calendar.working_days import saturday_occurrence

    assert _SAT_OFF.weekday() == 5 and saturday_occurrence(_SAT_OFF) == 4
    assert _SAT_WORKING.weekday() == 5 and saturday_occurrence(_SAT_WORKING) == 3
    assert _SUN.weekday() == 6
    assert _WEEKDAY.weekday() == 3


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


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="EMP001", first_name="Santosh",
                         last_name="Kumar")


def _run(db, dates):
    return generate_auto_reports(db, dates=dates)


# --- 1. normal Saturday -----------------------------------------------------


def test_normal_saturday_creates_an_auto_week_off_report(db, employee):
    result = _run(db, [_SAT_OFF])

    assert result.created == 1
    reports = _reports_for(db, employee.id, _SAT_OFF)
    assert len(reports) == 1
    report = reports[0]
    assert report.origin == ReportOrigin.auto
    assert report.day_status == DayStatus.week_off
    # Born SUBMITTED, not draft: a closed day has no reporting obligation left.
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


# --- 2. normal Sunday -------------------------------------------------------


def test_normal_sunday_creates_an_auto_week_off_report(db, employee):
    result = _run(db, [_SUN])

    assert result.created == 1
    report = _reports_for(db, employee.id, _SUN)[0]
    assert report.origin == ReportOrigin.auto
    assert report.day_status == DayStatus.week_off
    assert report.status == WorkReportStatus.submitted
    assert report.total_minutes == 0
    assert report.submitted_at is not None


def test_a_normal_weekday_creates_nothing(db, employee):
    result = _run(db, [_WEEKDAY])

    assert result.created == 0
    assert result.working_dates == 1
    assert _reports_for(db, employee.id) == []


def test_a_working_saturday_by_the_office_week_creates_nothing(db, employee):
    """The 3rd Saturday is a working day with no calendar entry involved."""
    result = _run(db, [_SAT_WORKING])

    assert result.created == 0
    assert _reports_for(db, employee.id) == []


# --- 3. working_day override (the rule this phase exists to protect) --------


def test_working_day_override_suppresses_the_auto_report(db, employee):
    """A non-working Saturday the PM has declared a WORKING_DAY gets no AUTO
    report. The override beats the weekend rule inside `is_working_day`, so it
    never reaches the create branch."""
    _calendar_event(db, event_date=_SAT_OFF, event_type="working_day",
                    title="Working Saturday")

    result = _run(db, [_SAT_OFF])

    assert result.created == 0
    assert result.working_dates == 1
    assert _reports_for(db, employee.id, _SAT_OFF) == []


def test_working_day_override_suppresses_the_auto_report_on_a_sunday(db, employee):
    _calendar_event(db, event_date=_SUN, event_type="working_day")

    assert _run(db, [_SUN]).created == 0
    assert _reports_for(db, employee.id, _SUN) == []


def test_working_day_override_on_one_date_does_not_affect_the_other(db, employee):
    """Only the overridden Saturday is spared; the Sunday beside it still gets
    its report, so the override is date-scoped and not a global switch."""
    _calendar_event(db, event_date=_SAT_OFF, event_type="working_day")

    result = _run(db, [_SAT_OFF, _SUN])

    assert result.created == 1
    assert _reports_for(db, employee.id, _SAT_OFF) == []
    assert len(_reports_for(db, employee.id, _SUN)) == 1


def test_ensure_auto_report_loads_the_calendar_itself_when_not_given_it(db, employee):
    """The single-employee entry point stands alone: called with no override
    sets it reads the calendar for that one date, so the override still wins."""
    _calendar_event(db, event_date=_SAT_OFF, event_type="working_day")

    outcome = ensure_auto_report(db, employee, _SAT_OFF)

    assert outcome.reason == "working_day"
    assert outcome.created is False
    assert _reports_for(db, employee.id, _SAT_OFF) == []


# --- 4. an existing employee report is never touched ------------------------


def _employee_report(db, employee_id, report_date):
    report = DailyWorkReport(
        employee_id=employee_id,
        report_date=report_date,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        remarks="Came in on the weekend",
        total_minutes=480,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_existing_employee_report_is_preserved_untouched(db, employee):
    existing = _employee_report(db, employee.id, _SAT_OFF)
    existing_id = existing.id

    result = _run(db, [_SAT_OFF])

    assert result.created == 0
    assert result.skipped_existing == 1
    reports = _reports_for(db, employee.id, _SAT_OFF)
    assert len(reports) == 1
    kept = reports[0]
    assert kept.id == existing_id
    # Not overwritten, not restamped, not relabelled, not deleted.
    assert kept.origin == ReportOrigin.employee
    assert kept.day_status == DayStatus.work_at_office
    assert kept.status == WorkReportStatus.submitted
    assert kept.total_minutes == 480
    assert kept.remarks == "Came in on the weekend"


def test_an_existing_draft_also_blocks_generation(db, employee):
    """The slot is taken by ANY report, whatever its status - the unique
    constraint does not care, so neither does the generator."""
    draft = DailyWorkReport(
        employee_id=employee.id,
        report_date=_SAT_OFF,
        status=WorkReportStatus.draft,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.comp_off,
        total_minutes=0,
    )
    db.add(draft)
    db.commit()

    assert _run(db, [_SAT_OFF]).created == 0
    reports = _reports_for(db, employee.id, _SAT_OFF)
    assert len(reports) == 1
    assert reports[0].origin == ReportOrigin.employee
    assert reports[0].day_status == DayStatus.comp_off


# --- 5. an existing AUTO report is not duplicated ---------------------------


def test_existing_auto_report_is_not_duplicated(db, employee):
    first = _run(db, [_SAT_OFF])
    assert first.created == 1
    original_id = _reports_for(db, employee.id, _SAT_OFF)[0].id

    second = _run(db, [_SAT_OFF])

    assert second.created == 0
    assert second.skipped_existing == 1
    reports = _reports_for(db, employee.id, _SAT_OFF)
    assert len(reports) == 1
    assert reports[0].id == original_id


# --- 6. multiple employees --------------------------------------------------


def test_every_employee_without_a_report_gets_exactly_one(db, make_employee):
    a = make_employee(employee_code="EMP-A", first_name="Aarthi")
    b = make_employee(employee_code="EMP-B", first_name="Bala")
    c = make_employee(employee_code="EMP-C", first_name="Chitra")

    result = _run(db, [_SAT_OFF])

    assert result.employees_considered == 3
    assert result.created == 3
    for emp in (a, b, c):
        reports = _reports_for(db, emp.id, _SAT_OFF)
        assert len(reports) == 1, emp.employee_code
        assert reports[0].origin == ReportOrigin.auto
        assert reports[0].day_status == DayStatus.week_off


def test_only_the_employees_without_a_report_get_one(db, make_employee):
    a = make_employee(employee_code="EMP-A")
    b = make_employee(employee_code="EMP-B")
    _employee_report(db, b.id, _SAT_OFF)

    result = _run(db, [_SAT_OFF])

    assert result.created == 1
    assert result.skipped_existing == 1
    assert _reports_for(db, a.id, _SAT_OFF)[0].origin == ReportOrigin.auto
    assert _reports_for(db, b.id, _SAT_OFF)[0].origin == ReportOrigin.employee


# --- 7. idempotency ---------------------------------------------------------


def test_running_the_generator_twice_creates_no_duplicates(db, make_employee):
    employees = [make_employee(employee_code=f"EMP-{i}") for i in range(3)]
    weekend = [_SAT_OFF, _SUN]

    first = _run(db, weekend)
    assert first.created == 6  # 3 employees x 2 non-working days
    total_after_first = db.query(DailyWorkReport).count()
    assert total_after_first == 6

    second = _run(db, weekend)
    assert second.created == 0
    assert db.query(DailyWorkReport).count() == total_after_first

    third = _run(db, weekend)
    assert third.created == 0
    assert db.query(DailyWorkReport).count() == total_after_first

    # One employee + one date = one report, still.
    for emp in employees:
        for day in weekend:
            assert len(_reports_for(db, emp.id, day)) == 1


def test_the_scheduled_window_sweep_is_idempotent(db, employee):
    """The real job sweeps `[today - lookback, today]`, which spans working and
    non-working days at once. Running it repeatedly must still settle."""
    monday_after = date(2026, 8, 24)

    first = generate_auto_reports(db, today=monday_after, lookback_days=7)
    second = generate_auto_reports(db, today=monday_after, lookback_days=7)

    assert second.created == 0
    # The swept range is 17-24 Aug 2026: Mon-Fri 17-21 are working, 24 Aug is a
    # Monday, so exactly two days are closed - Sat 22 (4th) and Sun 23.
    assert first.created == 2
    assert sorted(r.report_date for r in _reports_for(db, employee.id)) == [
        _SAT_OFF,
        _SUN,
    ]


# --- 8. future reconciliation safety ---------------------------------------


def test_auto_report_stays_identifiable_after_a_calendar_change(db, employee):
    """The stale-AUTO-report scenario the reconciliation phase must handle.

    Phase 3C does NOT reconcile. What it guarantees is that the row a later
    phase has to find is still findable by the only two facts that identify it:
    origin = auto and day_status = week_off. Nothing here may adopt, relabel, or
    silently convert that row - doing so would erase the evidence.
    """
    # 00:00 Saturday - the calendar says closed, so the report is filed.
    assert _run(db, [_SAT_OFF]).created == 1
    generated = _reports_for(db, employee.id, _SAT_OFF)[0]
    generated_id = generated.id

    # 07:00 Saturday - the PM declares it a working day after the fact.
    _calendar_event(db, event_date=_SAT_OFF, event_type="working_day")

    # A later run must neither delete it nor duplicate it. It is now STALE, and
    # staying put is the correct Phase 3C behaviour.
    assert _run(db, [_SAT_OFF]).created == 0

    # The reconciliation query a later phase will use, written out in full.
    stale = (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.origin == ReportOrigin.auto,
            DailyWorkReport.day_status == AUTO_WEEKEND_DAY_STATUS,
            DailyWorkReport.report_date == _SAT_OFF,
        )
        .all()
    )
    assert [r.id for r in stale] == [generated_id]


def test_reconciliation_query_never_catches_an_employees_own_week_off(db, make_employee):
    """The same query must not sweep up a week_off report the employee typed
    themselves. `origin` is what separates them, which is why it must never be
    rewritten."""
    auto_emp = make_employee(employee_code="EMP-AUTO")
    typed_emp = make_employee(employee_code="EMP-TYPED")
    typed = DailyWorkReport(
        employee_id=typed_emp.id,
        report_date=_SAT_OFF,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.week_off,
        total_minutes=0,
    )
    db.add(typed)
    db.commit()

    _run(db, [_SAT_OFF])

    stale = (
        db.query(DailyWorkReport)
        .filter(
            DailyWorkReport.origin == ReportOrigin.auto,
            DailyWorkReport.day_status == AUTO_WEEKEND_DAY_STATUS,
            DailyWorkReport.report_date == _SAT_OFF,
        )
        .all()
    )
    assert [r.employee_id for r in stale] == [auto_emp.id]


# --- employee population ----------------------------------------------------


def test_project_manager_logins_are_not_given_auto_reports(db, make_user,
                                                           make_employee):
    from app.modules.users.models import UserRole

    pm_user = make_user("pm@example.com", role=UserRole.project_manager)
    pm_emp = make_employee(employee_code="EMP-PM", user_id=pm_user.id)
    staff = make_employee(employee_code="EMP-STAFF")

    result = _run(db, [_SAT_OFF])

    assert result.created == 1
    assert _reports_for(db, pm_emp.id) == []
    assert len(_reports_for(db, staff.id, _SAT_OFF)) == 1


def test_non_active_and_deleted_employees_are_skipped(db, make_employee):
    """`status == active` and `deleted_at IS NULL` - the same pair the daily
    report reminder and the leave balance notice select employees by. An exited
    employee has no weekends to file."""
    from datetime import datetime, timezone

    from app.modules.employees.models import EmployeeStatus

    exited = make_employee(employee_code="EMP-EXITED", status=EmployeeStatus.exited)
    deleted = make_employee(employee_code="EMP-DELETED")
    deleted.deleted_at = datetime.now(timezone.utc)
    db.commit()
    active = make_employee(employee_code="EMP-ACTIVE")

    result = _run(db, [_SAT_OFF])

    assert result.created == 1
    assert _reports_for(db, exited.id) == []
    assert _reports_for(db, deleted.id) == []
    assert len(_reports_for(db, active.id, _SAT_OFF)) == 1


def test_a_day_before_the_employee_joined_is_never_generated(db, make_employee):
    joiner = make_employee(employee_code="EMP-NEW")
    joiner.date_of_joining = date(2026, 8, 24)  # the Monday after
    db.commit()

    assert _run(db, [_SAT_OFF]).created == 0
    assert _reports_for(db, joiner.id) == []
    assert report_submitters(db, _SAT_OFF) == []
    # ...and the joining day's own weekend IS generated.
    assert _run(db, [date(2026, 8, 29)]).created == 0  # 5th Sat = working
    assert _run(db, [date(2026, 8, 30)]).created == 1  # Sunday after joining


def test_no_employees_at_all_is_not_an_error(db):
    result = _run(db, [_SAT_OFF])

    assert result.created == 0
    assert result.employees_considered == 0
    assert db.query(DailyWorkReport).count() == 0


# --- the report row shape ---------------------------------------------------


def test_the_auto_report_gets_a_full_day_period_like_a_typed_one(db, employee):
    """An AUTO report is the same row shape an employee's full-day week_off
    report has, so nothing that reads periods needs a special case."""
    from decimal import Decimal

    from app.modules.work_reports.models import DayPart, WorkReportPeriod

    _run(db, [_SAT_OFF])
    report = _reports_for(db, employee.id, _SAT_OFF)[0]

    periods = (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report.id)
        .all()
    )
    assert len(periods) == 1
    period = periods[0]
    assert period.day_part == DayPart.full_day.value
    assert period.period_status == DayStatus.week_off
    assert period.work_fraction == Decimal("1.0")
    assert period.is_legacy_half_day is False


def test_the_auto_report_carries_no_task_lines(db, employee):
    from app.modules.work_reports.models import WorkReportTask

    _run(db, [_SAT_OFF])
    report = _reports_for(db, employee.id, _SAT_OFF)[0]

    assert (
        db.query(WorkReportTask)
        .filter(WorkReportTask.report_id == report.id)
        .count()
        == 0
    )


def test_generate_returns_the_dates_it_swept(db, employee):
    result = generate_auto_reports(db, today=date(2026, 8, 24), lookback_days=2)

    assert result.dates == [date(2026, 8, 22), date(2026, 8, 23), date(2026, 8, 24)]
    assert result.working_dates == 1  # Monday 24 Aug
    assert result.created == 2
    assert sorted(r.report_date for r in _reports_for(db, employee.id)) == [
        _SAT_OFF,
        _SUN,
    ]


# --- submitted is not locked: editability --------------------------------


@pytest.fixture()
def author(make_user, make_employee):
    """An employee with a login, so the report service can resolve them as the
    author of their own report."""
    user = make_user("author@example.com")
    emp = make_employee(employee_code="EMP-AUTHOR", user_id=user.id)
    return user, emp


def test_auto_weekend_report_is_editable_by_its_author(db, author):
    """Rule: AUTO + week_off -> editable. `submitted` here means "the day is
    accounted for", never "locked"."""
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.schemas import WorkReportUpdate

    user, emp = author
    _run(db, [_SAT_OFF])
    report = _reports_for(db, emp.id, _SAT_OFF)[0]
    assert report.status == WorkReportStatus.submitted

    updated = svc.update_work_report(
        db, user, report.id, WorkReportUpdate(remarks="Was called in briefly")
    )

    assert updated.remarks == "Was called in briefly"
    # Reopened to draft by the SAME mechanism a Project Head's self-edit uses,
    # so benchmarks recompute on resubmit and nothing is mutated while still
    # marked submitted.
    assert updated.status == WorkReportStatus.draft
    assert updated.submitted_at is None
    # The edit does not convert the row: reconciliation must still find it.
    assert updated.origin == ReportOrigin.auto
    assert updated.day_status == DayStatus.week_off


def test_can_self_edit_is_advertised_for_an_auto_weekend_report(db, author):
    """The UI flag and the write-side guard must agree, so the flag is true for
    exactly the report the previous test can edit."""
    from app.modules.work_reports import service as svc

    user, emp = author
    _run(db, [_SAT_OFF])
    report_id = _reports_for(db, emp.id, _SAT_OFF)[0].id

    fetched = svc.get_work_report(db, user, report_id)

    assert fetched.status == WorkReportStatus.submitted
    assert fetched.can_self_edit is True


def test_auto_leave_report_is_locked_to_its_author(db, author):
    """Rule: AUTO + leave -> locked while the leave is active. Phase 3C never
    generates one, so it is built by hand here; the guard exists so the phase
    that does start generating them cannot forget the lock."""
    from app.shared.errors import AppError
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.schemas import WorkReportUpdate

    user, emp = author
    locked = DailyWorkReport(
        employee_id=emp.id,
        report_date=_SAT_OFF,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.auto,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.leave,
        total_minutes=0,
    )
    db.add(locked)
    db.commit()
    db.refresh(locked)

    with pytest.raises(AppError) as exc:
        svc.update_work_report(db, user, locked.id, WorkReportUpdate(remarks="nope"))

    assert exc.value.status_code == 403
    db.rollback()
    db.refresh(locked)
    assert locked.status == WorkReportStatus.submitted
    assert locked.remarks is None


def test_an_employee_submitted_report_is_still_locked(db, author):
    """Regression guard on the exemption's blast radius: it may only ever ADD
    permission to an origin=auto row, never to a person's own report."""
    from app.shared.errors import AppError
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.schemas import WorkReportUpdate

    user, emp = author
    typed = DailyWorkReport(
        employee_id=emp.id,
        report_date=_SAT_OFF,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.week_off,
        total_minutes=0,
    )
    db.add(typed)
    db.commit()
    db.refresh(typed)

    with pytest.raises(AppError) as exc:
        svc.update_work_report(db, user, typed.id, WorkReportUpdate(remarks="nope"))

    assert exc.value.status_code == 403
    db.rollback()
    db.refresh(typed)
    assert typed.status == WorkReportStatus.submitted
    assert typed.remarks is None


def test_auto_report_author_editable_predicate(db, employee):
    """The predicate itself, over the four cases that matter."""
    from app.modules.work_reports.auto_reports import auto_report_author_editable

    def _row(origin, day_status):
        return DailyWorkReport(
            employee_id=employee.id,
            report_date=_SAT_OFF,
            status=WorkReportStatus.submitted,
            origin=origin,
            report_mode=ReportMode.full_day.value,
            day_status=day_status,
            total_minutes=0,
        )

    assert auto_report_author_editable(_row(ReportOrigin.auto, DayStatus.week_off))
    assert auto_report_author_editable(
        _row(ReportOrigin.auto, DayStatus.company_holiday)
    )
    # The one locked case.
    assert not auto_report_author_editable(_row(ReportOrigin.auto, DayStatus.leave))
    # An employee's own report is never granted anything by this predicate.
    assert not auto_report_author_editable(
        _row(ReportOrigin.employee, DayStatus.week_off)
    )
