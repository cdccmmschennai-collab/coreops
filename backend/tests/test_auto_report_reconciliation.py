"""Phase 3D - reconciling AUTO week-off reports when a closed date becomes a
working one.

THE SEQUENCE UNDER TEST
=======================
    Saturday 00:00  calendar says closed      -> AUTO week_off report generated
    Saturday 07:00  PM declares it a WORKING DAY
                    -> that report is now wrong

The generator cannot fix it (it only ever creates, and an existing report always
wins), so the calendar write does: every create / update / delete in
`calendar.service` calls
`auto_reports.reconcile_auto_reports_for_calendar_change` for the dates it may
have re-classified.

TWO OUTCOMES
============
    untouched AUTO row -> DELETED, freeing the date for a normal report
    row with anybody's data on it -> PRESERVED, only the week_off label removed

and the second one is the default: `is_untouched_auto_report` matches the
generated signature in full, so anything unrecognised is preserved.

CALENDAR ANCHORS
================
August 2026 starts on a Saturday, so its Saturdays are the 1st/2nd/3rd/4th/5th on
the 1st/8th/15th/22nd/29th. Only the 2nd and 4th Saturday are off, which makes
22 Aug genuinely non-working and 15 Aug a working Saturday.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.calendar import service as calendar_service
from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.schemas import CalendarEventCreate, CalendarEventUpdate
from app.modules.users.models import UserRole
from app.modules.work_reports.auto_reports import (
    AUTO_WEEKEND_DAY_STATUS,
    generate_auto_reports,
    is_untouched_auto_report,
    reconcile_auto_reports_for_calendar_change,
)
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayPart,
    DayStatus,
    ReportMode,
    ReportOrigin,
    WorkLocation,
    WorkReportPeriod,
    WorkReportStatus,
    WorkReportTask,
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


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="EMP001", first_name="Santosh",
                         last_name="Kumar")


@pytest.fixture()
def author(make_user, make_employee):
    """An employee with a login, so the report service can resolve them as the
    author of their own report."""
    user = make_user("author@example.com")
    emp = make_employee(employee_code="EMP-AUTHOR", user_id=user.id)
    return user, emp


@pytest.fixture()
def pm(make_user):
    return make_user("pm@example.com", role=UserRole.project_manager)


def _calendar_event(db, *, event_date, event_type, title="Test"):
    """A calendar row written DIRECTLY - no service, so no reconciliation. Used
    to set the calendar up before the run being tested."""
    ev = CalendarEvent(
        event_date=event_date, title=title, event_type=CalendarEventType(event_type)
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _generate(db, dates):
    return generate_auto_reports(db, dates=dates)


def _reports_for(db, employee_id, report_date=None):
    q = db.query(DailyWorkReport).filter(DailyWorkReport.employee_id == employee_id)
    if report_date is not None:
        q = q.filter(DailyWorkReport.report_date == report_date)
    return q.all()


def _the_report(db, employee_id, report_date=_SAT_OFF):
    reports = _reports_for(db, employee_id, report_date)
    assert len(reports) == 1, reports
    return reports[0]


def _periods(db, report_id):
    return (
        db.query(WorkReportPeriod)
        .filter(WorkReportPeriod.report_id == report_id)
        .all()
    )


def _tasks(db, report_id):
    return (
        db.query(WorkReportTask).filter(WorkReportTask.report_id == report_id).all()
    )


def _make_working(db, day=_SAT_OFF):
    """Declare `day` a working day the way a PM does, without going through the
    calendar service (so the test drives reconciliation itself)."""
    return _calendar_event(db, event_date=day, event_type="working_day",
                           title="Working Saturday")


def _reconcile(db, dates=(_SAT_OFF,)):
    return reconcile_auto_reports_for_calendar_change(db, list(dates))


# --- A. untouched AUTO weekend report -> WORKING_DAY ------------------------


def test_untouched_auto_report_is_deleted_when_the_date_becomes_working(db, employee):
    assert _generate(db, [_SAT_OFF]).created == 1
    report = _the_report(db, employee.id)
    report_id = report.id
    assert report.origin == ReportOrigin.auto
    assert report.day_status == AUTO_WEEKEND_DAY_STATUS
    assert _periods(db, report_id)  # it has its generated Full-Day period

    _make_working(db)
    result = _reconcile(db)

    assert result.examined == 1
    assert result.deleted == 1
    assert result.reclassified == 0
    assert [o.action for o in result.outcomes] == ["deleted"]
    assert _reports_for(db, employee.id, _SAT_OFF) == []


def test_the_deleted_reports_child_rows_go_with_it(db, employee):
    """The delete leans on the existing ON DELETE CASCADE, so no period (and no
    task row, were there one) is left orphaned."""
    _generate(db, [_SAT_OFF])
    report_id = _the_report(db, employee.id).id
    assert len(_periods(db, report_id)) == 1

    _make_working(db)
    _reconcile(db)

    assert _periods(db, report_id) == []
    assert _tasks(db, report_id) == []


def test_after_deletion_the_employee_can_file_a_normal_report(db, author):
    """The point of deleting: the (employee, date) slot is free again, so the
    ordinary create path works on what is now an ordinary working day."""
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.schemas import WorkReportCreate

    user, emp = author
    _generate(db, [_SAT_OFF])
    assert len(_reports_for(db, emp.id, _SAT_OFF)) == 1

    _make_working(db)
    _reconcile(db)

    created = svc.create_work_report(
        db,
        user,
        WorkReportCreate(
            report_date=_SAT_OFF,
            day_status=DayStatus.comp_off,
            tasks=[],
        ),
    )
    assert created.origin == ReportOrigin.employee
    assert created.status == WorkReportStatus.draft
    assert len(_reports_for(db, emp.id, _SAT_OFF)) == 1


def test_reconciliation_creates_no_replacement_report(db, make_employee):
    a = make_employee(employee_code="EMP-A")
    b = make_employee(employee_code="EMP-B")
    assert _generate(db, [_SAT_OFF]).created == 2

    _make_working(db)
    _reconcile(db)

    assert db.query(DailyWorkReport).count() == 0
    assert _reports_for(db, a.id) == []
    assert _reports_for(db, b.id) == []


# --- B. AUTO weekend report that carries employee work ----------------------


def test_an_edited_auto_report_is_preserved_and_reclassified(db, author):
    """The realistic Case B: the author edits the AUTO week-off report (which
    reopens it to draft) and only then does the PM open the Saturday."""
    from app.modules.work_reports import service as svc
    from app.modules.work_reports.schemas import WorkReportUpdate

    user, emp = author
    _generate(db, [_SAT_OFF])
    report_id = _the_report(db, emp.id).id
    svc.update_work_report(
        db, user, report_id, WorkReportUpdate(remarks="Was called in briefly")
    )

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 0
    assert result.reclassified == 1
    kept = _the_report(db, emp.id)
    assert kept.id == report_id
    # The employee's words survive untouched...
    assert kept.remarks == "Was called in briefly"
    # ...the obsolete classification does not...
    assert kept.day_status is None
    # ...and the row remains historically honest about who created it.
    assert kept.origin == ReportOrigin.auto


def test_an_auto_report_with_task_rows_keeps_every_one_of_them(db, employee,
                                                               make_project):
    """Belt and braces for the rule that matters most: whatever put work rows on
    an AUTO week-off report, reconciliation must not lose them."""
    project = make_project(code="P-1", name="Pipeline")
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    period = _periods(db, report.id)[0]
    db.add(
        WorkReportTask(
            report_id=report.id,
            period_id=period.id,
            project_id=project.id,
            description="Emergency call-out",
            minutes_spent=180,
        )
    )
    report.total_minutes = 180
    db.commit()

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 0
    assert result.reclassified == 1
    kept = _the_report(db, employee.id)
    assert kept.total_minutes == 180
    tasks = _tasks(db, kept.id)
    assert [t.description for t in tasks] == ["Emergency call-out"]
    assert [t.minutes_spent for t in tasks] == [180]
    assert kept.day_status is None
    assert kept.origin == ReportOrigin.auto


def test_reclassification_reopens_a_submitted_report_to_draft(db, employee,
                                                              make_project):
    """A submitted report declares the day accounted for. Stripped of its
    week_off status it accounts for nothing, so it goes back to the employee as a
    draft - by the existing reopen (status AND submitted_at together), not a new
    state."""
    project = make_project(code="P-1")
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    assert report.status == WorkReportStatus.submitted
    db.add(
        WorkReportTask(
            report_id=report.id,
            period_id=_periods(db, report.id)[0].id,
            project_id=project.id,
            description="Call-out",
        )
    )
    db.commit()

    _make_working(db)
    _reconcile(db)

    kept = _the_report(db, employee.id)
    assert kept.status == WorkReportStatus.draft
    assert kept.submitted_at is None


def test_reclassification_clears_the_week_off_status_on_the_period_too(db, employee):
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    report.remarks = "Worked a few hours"
    db.commit()

    _make_working(db)
    _reconcile(db)

    periods = _periods(db, report.id)
    assert len(periods) == 1
    assert periods[0].period_status is None
    # The Full-Day period is a whole day with or without a status.
    assert periods[0].work_fraction == Decimal("1.0")
    assert periods[0].day_part == DayPart.full_day.value


def test_a_draft_auto_report_keeps_its_status_on_reclassification(db, employee):
    """Only a `submitted` row is reopened; one already in draft is left in draft
    rather than being pushed through a state it is already in."""
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    report.status = WorkReportStatus.draft
    report.submitted_at = None
    report.remarks = "Half a day on site"
    db.commit()

    _make_working(db)
    _reconcile(db)

    kept = _the_report(db, employee.id)
    assert kept.status == WorkReportStatus.draft
    assert kept.day_status is None
    assert kept.remarks == "Half a day on site"


# --- C. an employee-authored week_off report is never touched ---------------


def _employee_week_off_report(db, employee_id, report_date=_SAT_OFF):
    report = DailyWorkReport(
        employee_id=employee_id,
        report_date=report_date,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.week_off,
        total_minutes=0,
        remarks="Took the Saturday off",
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def test_an_employee_authored_week_off_report_is_left_alone(db, employee):
    """`origin` is the only thing separating the two, which is why nothing may
    ever rewrite it."""
    typed = _employee_week_off_report(db, employee.id)
    typed_id = typed.id

    _make_working(db)
    result = _reconcile(db)

    assert result.examined == 0
    assert result.deleted == 0
    assert result.reclassified == 0
    kept = _the_report(db, employee.id)
    assert kept.id == typed_id
    assert kept.origin == ReportOrigin.employee
    assert kept.day_status == DayStatus.week_off
    assert kept.status == WorkReportStatus.submitted
    assert kept.remarks == "Took the Saturday off"


def test_an_employee_report_beside_an_auto_one_is_untouched(db, make_employee):
    """Same date, two employees: only the generated row is reconciled."""
    typed_emp = make_employee(employee_code="EMP-TYPED")
    auto_emp = make_employee(employee_code="EMP-AUTO")
    _employee_week_off_report(db, typed_emp.id)
    assert _generate(db, [_SAT_OFF]).created == 1  # only for auto_emp

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 1
    assert _reports_for(db, auto_emp.id, _SAT_OFF) == []
    kept = _the_report(db, typed_emp.id)
    assert kept.origin == ReportOrigin.employee
    assert kept.day_status == DayStatus.week_off


def test_an_auto_leave_report_is_out_of_scope(db, employee):
    """Phase 3D reconciles `week_off` only. An automatic LEAVE report belongs to
    a later phase and must not be swept up by this one."""
    leave_report = DailyWorkReport(
        employee_id=employee.id,
        report_date=_SAT_OFF,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.auto,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.leave,
        total_minutes=0,
    )
    db.add(leave_report)
    db.commit()

    _make_working(db)
    result = _reconcile(db)

    assert result.examined == 0
    kept = _the_report(db, employee.id)
    assert kept.day_status == DayStatus.leave
    assert kept.status == WorkReportStatus.submitted


# --- D. zero minutes is NOT proof the report is untouched -------------------


def _mutate(db, report, **fields):
    for key, value in fields.items():
        setattr(report, key, value)
    db.commit()
    db.refresh(report)


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("remarks", "Came in for two hours"),
        ("query_text", "Who signs the OT slip?"),
        ("summary", "Weekend call-out"),
        ("well_head_no", "WH-42"),
        ("pm_plant", "Plant 3"),
        ("location", WorkLocation.chennai),
        ("task_list_count", 5),
        ("task_list_op_count", 3),
        ("maintenance_item_count", 7),
        ("maintenance_plan_count", 2),
    ],
)
def test_any_employee_entered_field_prevents_deletion(db, employee, field_name,
                                                      value):
    """Every one of these can be typed onto a week-off report without adding a
    single minute - the day status drops task lines on every write path - so
    `total_minutes == 0` can never be the deletion test on its own."""
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    _mutate(db, report, **{field_name: value})
    assert report.total_minutes == 0

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 0
    assert result.reclassified == 1
    kept = _the_report(db, employee.id)
    assert getattr(kept, field_name) == value
    assert kept.day_status is None
    assert kept.origin == ReportOrigin.auto


def test_a_stamped_updated_by_prevents_deletion(db, employee, make_user):
    """The generator writes no actor at all, so any `updated_by` means a person
    went through a write path - even if they changed nothing else."""
    someone = make_user("someone@example.com")
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    _mutate(db, report, updated_by=someone.id)

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 0
    assert _the_report(db, employee.id).id == report.id


def test_a_period_remark_prevents_deletion(db, employee):
    """The evidence can sit on the period rather than the header."""
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    period = _periods(db, report.id)[0]
    period.remarks = "In for the morning"
    db.commit()

    _make_working(db)
    result = _reconcile(db)

    assert result.deleted == 0
    assert result.reclassified == 1
    assert _the_report(db, employee.id).id == report.id
    assert _periods(db, report.id)[0].remarks == "In for the morning"


def test_the_untouched_signature_over_the_whole_row(db, employee, make_project):
    """The predicate itself, field by field: True for exactly what the generator
    writes and False for every single deviation from it."""
    project = make_project(code="P-1")
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    assert is_untouched_auto_report(db, report) is True

    # An author edit reopens the report to draft - never untouched again.
    _mutate(db, report, status=WorkReportStatus.draft, submitted_at=None)
    assert is_untouched_auto_report(db, report) is False
    _mutate(db, report, status=WorkReportStatus.submitted)
    assert is_untouched_auto_report(db, report) is False  # submitted_at is NULL

    from datetime import datetime, timezone

    _mutate(db, report, submitted_at=datetime.now(timezone.utc))
    assert is_untouched_auto_report(db, report) is True

    _mutate(db, report, total_minutes=60)
    assert is_untouched_auto_report(db, report) is False
    _mutate(db, report, total_minutes=0)

    _mutate(db, report, report_mode=ReportMode.split_day.value)
    assert is_untouched_auto_report(db, report) is False
    _mutate(db, report, report_mode=ReportMode.full_day.value)

    _mutate(db, report, origin=ReportOrigin.employee)
    assert is_untouched_auto_report(db, report) is False
    _mutate(db, report, origin=ReportOrigin.auto)

    _mutate(db, report, day_status=DayStatus.comp_off)
    assert is_untouched_auto_report(db, report) is False
    _mutate(db, report, day_status=AUTO_WEEKEND_DAY_STATUS)
    assert is_untouched_auto_report(db, report) is True

    # A task row is decisive on its own.
    db.add(
        WorkReportTask(
            report_id=report.id,
            period_id=_periods(db, report.id)[0].id,
            project_id=project.id,
            description="Call-out",
        )
    )
    db.commit()
    assert is_untouched_auto_report(db, report) is False


def test_a_report_with_no_period_row_is_still_untouched(db, employee):
    """Pre-period rows carry no period at all; that is an absence of data, not
    evidence of any."""
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    for period in _periods(db, report.id):
        db.delete(period)
    db.commit()

    assert is_untouched_auto_report(db, report) is True

    _make_working(db)
    assert _reconcile(db).deleted == 1


# --- E. idempotency ---------------------------------------------------------


def test_running_reconciliation_twice_is_harmless_after_a_delete(db, employee):
    _generate(db, [_SAT_OFF])
    _make_working(db)

    first = _reconcile(db)
    assert first.deleted == 1
    assert db.query(DailyWorkReport).count() == 0

    second = _reconcile(db)
    third = _reconcile(db)

    assert second.examined == 0 and second.deleted == 0 and second.reclassified == 0
    assert third.examined == 0
    assert db.query(DailyWorkReport).count() == 0


def test_running_reconciliation_twice_is_harmless_after_a_reclassify(db, employee):
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    _mutate(db, report, remarks="Came in")
    _make_working(db)

    first = _reconcile(db)
    assert first.reclassified == 1
    after_first = _the_report(db, employee.id)
    snapshot = (
        after_first.id,
        after_first.status,
        after_first.day_status,
        after_first.remarks,
        after_first.origin,
        after_first.total_minutes,
    )

    second = _reconcile(db)

    # The row is out of scope now - its day_status no longer says week_off.
    assert second.examined == 0
    assert second.reclassified == 0
    after_second = _the_report(db, employee.id)
    assert (
        after_second.id,
        after_second.status,
        after_second.day_status,
        after_second.remarks,
        after_second.origin,
        after_second.total_minutes,
    ) == snapshot
    assert db.query(DailyWorkReport).count() == 1


def test_reconciling_a_date_that_is_still_non_working_does_nothing(db, employee):
    """The reverse direction and the no-op case in one: the Saturday is still
    closed, so the AUTO report is still correct and stays exactly as it is."""
    _generate(db, [_SAT_OFF])
    report_id = _the_report(db, employee.id).id

    result = _reconcile(db, [_SAT_OFF, _SUN])

    assert result.still_non_working == 2
    assert result.examined == 0
    assert result.deleted == 0
    kept = _the_report(db, employee.id)
    assert kept.id == report_id
    assert kept.day_status == AUTO_WEEKEND_DAY_STATUS
    assert kept.status == WorkReportStatus.submitted


def test_reconciliation_never_generates_for_a_date_turning_non_working(db, employee):
    """WORKING_DAY -> WEEKEND is the 01:00 generator's job, not this function's:
    reconciliation must not file anything."""
    ev = _calendar_event(db, event_date=_SAT_OFF, event_type="working_day")
    assert _generate(db, [_SAT_OFF]).created == 0

    db.delete(ev)  # the Saturday closes again
    db.commit()
    result = _reconcile(db)

    assert result.still_non_working == 1
    assert result.examined == 0
    assert _reports_for(db, employee.id) == []


def test_only_the_changed_date_is_reconciled(db, employee):
    """A weekend is two dates; opening the Saturday must not disturb the
    Sunday's report."""
    assert _generate(db, [_SAT_OFF, _SUN]).created == 2

    _make_working(db, _SAT_OFF)
    result = _reconcile(db, [_SAT_OFF])

    assert result.deleted == 1
    assert _reports_for(db, employee.id, _SAT_OFF) == []
    sunday = _the_report(db, employee.id, _SUN)
    assert sunday.day_status == AUTO_WEEKEND_DAY_STATUS
    assert sunday.status == WorkReportStatus.submitted


# --- F. every calendar operation that can open a closed date ----------------


def test_creating_a_working_day_event_reconciles_through_the_service(db, employee,
                                                                     pm):
    """The real path: POST /calendar-events with a working_day on the Saturday."""
    _generate(db, [_SAT_OFF])
    assert len(_reports_for(db, employee.id, _SAT_OFF)) == 1

    calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_SAT_OFF, title="Working Saturday", event_type="working_day"
        ),
    )

    assert _reports_for(db, employee.id, _SAT_OFF) == []


def test_creating_a_working_day_event_preserves_a_worked_auto_report(db, employee,
                                                                     pm):
    _generate(db, [_SAT_OFF])
    report = _the_report(db, employee.id)
    _mutate(db, report, remarks="Came in for the shutdown")

    calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_SAT_OFF, title="Working Saturday", event_type="working_day"
        ),
    )

    kept = _the_report(db, employee.id)
    assert kept.id == report.id
    assert kept.remarks == "Came in for the shutdown"
    assert kept.day_status is None
    assert kept.origin == ReportOrigin.auto


def test_deleting_a_holiday_reconciles_the_weekday_it_closed(db, employee, pm):
    """A declared holiday on a WEEKDAY closes the office, so Phase 3C generates
    for it. Deleting the holiday re-opens that weekday and the report is stale."""
    holiday = calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_WEEKDAY, title="Company holiday", event_type="holiday"
        ),
    )
    assert _generate(db, [_WEEKDAY]).created == 1
    assert len(_reports_for(db, employee.id, _WEEKDAY)) == 1

    calendar_service.delete_event(db, pm, holiday.id)

    assert _reports_for(db, employee.id, _WEEKDAY) == []


def test_deleting_a_working_day_override_reconciles_nothing(db, employee, pm):
    """The other deletion: removing a working_day CLOSES the Saturday again.
    There is nothing stale to remove and nothing may be created."""
    override = calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_SAT_OFF, title="Working Saturday", event_type="working_day"
        ),
    )
    assert _generate(db, [_SAT_OFF]).created == 0

    calendar_service.delete_event(db, pm, override.id)

    assert _reports_for(db, employee.id) == []


def test_changing_an_event_type_to_working_day_reconciles(db, employee, pm):
    """An informational `event` leaves the Saturday closed; re-typing it to
    `working_day` opens it."""
    ev = calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_SAT_OFF, title="Site visit", event_type="event"
        ),
    )
    assert _generate(db, [_SAT_OFF]).created == 1

    calendar_service.update_event(
        db, pm, ev.id, CalendarEventUpdate(event_type=CalendarEventType.working_day)
    )

    assert _reports_for(db, employee.id, _SAT_OFF) == []


def test_moving_a_working_day_event_onto_a_closed_date_reconciles(db, employee, pm):
    """The date, not the type, changes: the override lands on the closed
    Saturday, and the Sunday it left simply closes again (nothing to do there,
    and nothing may be created)."""
    ev = calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_SUN, title="Working Sunday", event_type="working_day"
        ),
    )
    # The Sunday is open, so only the Saturday gets a report.
    assert _generate(db, [_SAT_OFF, _SUN]).created == 1

    calendar_service.update_event(
        db, pm, ev.id, CalendarEventUpdate(event_date=_SAT_OFF)
    )

    assert _reports_for(db, employee.id, _SAT_OFF) == []
    # The Sunday closed again - the 01:00 generator files it, not this path.
    assert _reports_for(db, employee.id, _SUN) == []


def test_creating_a_holiday_closes_a_day_and_reconciles_nothing(db, employee, pm):
    """The closing direction through the service: an employee's report on the
    weekday is not touched, and no AUTO row appears."""
    typed = DailyWorkReport(
        employee_id=employee.id,
        report_date=_WEEKDAY,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        total_minutes=480,
    )
    db.add(typed)
    db.commit()

    calendar_service.create_event(
        db,
        pm,
        CalendarEventCreate(
            event_date=_WEEKDAY, title="Cyclone", event_type="natural_hazard"
        ),
    )

    kept = _the_report(db, employee.id, _WEEKDAY)
    assert kept.id == typed.id
    assert kept.day_status == DayStatus.work_at_office
    assert kept.total_minutes == 480


# --- G. an ordinary working day ---------------------------------------------


def test_reconciling_an_ordinary_working_day_touches_nothing(db, employee,
                                                             make_project):
    """No AUTO report can exist on a normal working day; the employee's own
    report there is out of scope on both counts."""
    project = make_project(code="P-1")
    typed = DailyWorkReport(
        employee_id=employee.id,
        report_date=_WEEKDAY,
        status=WorkReportStatus.submitted,
        origin=ReportOrigin.employee,
        report_mode=ReportMode.full_day.value,
        day_status=DayStatus.work_at_office,
        location=WorkLocation.chennai,
        remarks="Normal day",
        total_minutes=480,
    )
    db.add(typed)
    db.flush()
    db.add(
        WorkReportTask(
            report_id=typed.id,
            project_id=project.id,
            description="Tagging",
            minutes_spent=480,
        )
    )
    db.commit()

    result = _reconcile(db, [_WEEKDAY, _SAT_WORKING])

    assert result.still_non_working == 0  # both dates ARE working days
    assert result.examined == 0
    assert result.deleted == 0
    kept = _the_report(db, employee.id, _WEEKDAY)
    assert kept.day_status == DayStatus.work_at_office
    assert kept.status == WorkReportStatus.submitted
    assert kept.remarks == "Normal day"
    assert kept.total_minutes == 480
    assert len(_tasks(db, kept.id)) == 1


def test_an_empty_date_list_is_not_an_error(db, employee):
    _generate(db, [_SAT_OFF])

    result = reconcile_auto_reports_for_calendar_change(db, [])

    assert result.dates == []
    assert result.examined == 0
    assert len(_reports_for(db, employee.id, _SAT_OFF)) == 1
