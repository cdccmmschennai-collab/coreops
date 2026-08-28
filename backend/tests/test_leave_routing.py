"""Tests for leave-approval routing to Project Head.

`test_leave_routing.py` covers the resolver and its own smoke test that
`routed_project_id` persists and serializes. API-level behavior (notification
target, scope, authorization) lives in `test_leave_api.py` alongside the rest of
the leave RBAC suite it extends.

DATES ARE ANCHORED IN THE PAST
==============================
`work_reports.service` refuses a report dated after today, so every date these
tests build walks BACKWARDS from today. An earlier version anchored on the next
Monday and derived the report date from it, which put the report in the future
whenever today was a Thursday or Friday - the suite failed on those two days of
the week for reasons that had nothing to do with routing. `resolve_routed_project`
itself is a pure resolver with no opinion about the past or the future, so a
leave date in the past exercises it exactly as a real one would.
"""
from datetime import date, timedelta

from app.modules.calendar.working_days import previous_working_day
from app.modules.leave import routing
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn


def _task(project_id, minutes=120):
    return WorkReportTaskIn(project_id=project_id, description="work", minutes_spent=minutes)


def _working_days_back(db, count: int) -> list[date]:
    """The last `count` working days at-or-before today, MOST RECENT FIRST.

    `previous_working_day` is strictly-before, so it is seeded with tomorrow to
    make the first result "today, or the last working day before it".
    """
    days: list[date] = []
    cursor = date.today() + timedelta(days=1)
    for _ in range(count):
        cursor = previous_working_day(db, cursor)
        assert cursor is not None, "no working day found - calendar misconfigured"
        days.append(cursor)
    return days


def _recent_monday() -> date:
    """The most recent Monday strictly before today, so the Friday before it and
    the Saturday between them are both in the past and can carry a report."""
    day = date.today() - timedelta(days=1)
    while day.weekday() != 0:
        day -= timedelta(days=1)
    return day


def test_routed_project_id_persists(db, make_employee, make_user, make_project):
    u = make_user("emp@x.com")
    emp = make_employee(employee_code="E1", user_id=u.id)
    project = make_project(code="P-1")

    req = LeaveRequest(
        employee_id=emp.id,
        leave_type=LeaveType.casual,
        start_date=date.today(),
        end_date=date.today(),
        status=LeaveStatus.pending,
        routed_project_id=project.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    assert req.routed_project_id == project.id


# ---------- the evidence date ----------------------------------------------

def test_a_report_on_the_leave_start_date_is_the_evidence(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Report and leave on the SAME day. An employee who filed their report and
    then took the rest of the day off has already said which project they are
    on; the previous day is not more authoritative than that."""
    u = make_user("start@x.com")
    emp = make_employee(employee_code="ES1", user_id=u.id)
    today_project = make_project(code="EV-1")
    prev_project = make_project(code="EV-1B")
    make_project_member(project_id=today_project.id, employee_id=emp.id)
    make_project_member(project_id=prev_project.id, employee_id=emp.id)
    leave_day, prev_day = _working_days_back(db, 2)

    # A report on BOTH days, on different projects - the start date must win.
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(prev_project.id)])
    )
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=leave_day, tasks=[_task(today_project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) == today_project.id


def test_the_previous_working_day_is_used_when_the_start_date_has_no_report(
    db, make_user, make_employee, make_project, make_project_member,
):
    u = make_user("emp2@x.com")
    emp = make_employee(employee_code="E2", user_id=u.id)
    project = make_project(code="P-2")
    make_project_member(project_id=project.id, employee_id=emp.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) == project.id


def test_the_evidence_search_skips_the_weekend(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Monday's leave routes off Friday's report - Sat/Sun are never checked,
    proving previous_working_day (not a naive `date - 1`) drives the lookup."""
    u = make_user("emp3@x.com")
    emp = make_employee(employee_code="E3", user_id=u.id)
    project = make_project(code="P-3")
    other_project = make_project(code="P-3B")
    make_project_member(project_id=project.id, employee_id=emp.id)
    make_project_member(project_id=other_project.id, employee_id=emp.id)

    monday = _recent_monday()
    friday = monday - timedelta(days=3)
    saturday = monday - timedelta(days=2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, tasks=[_task(project.id)])
    )
    # A Saturday report must NOT be picked over Friday's.
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=saturday, tasks=[_task(other_project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, monday) == project.id


def test_a_non_working_start_date_is_never_read_as_evidence(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Leave starting on a Sunday. The start date is offered as evidence only
    when the calendar says it is a working day, so a stray weekend report cannot
    outrank Friday's real one."""
    u = make_user("weekend@x.com")
    emp = make_employee(employee_code="EW1", user_id=u.id)
    friday_project = make_project(code="EV-2")
    sunday_project = make_project(code="EV-2B")
    make_project_member(project_id=friday_project.id, employee_id=emp.id)
    make_project_member(project_id=sunday_project.id, employee_id=emp.id)

    monday = _recent_monday()
    friday = monday - timedelta(days=3)
    sunday = monday - timedelta(days=1)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, tasks=[_task(friday_project.id)])
    )
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=sunday, tasks=[_task(sunday_project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, sunday) == friday_project.id


def test_an_unusable_report_on_the_start_date_does_not_reach_past_it(
    db, make_user, make_employee, make_project, make_project_member,
):
    """The start date has a report, but it spans two projects. That report IS the
    evidence and it is ambiguous, so the answer is the PM - the resolver does not
    reach back to the previous day hunting for a cleaner one."""
    u = make_user("ambig-start@x.com")
    emp = make_employee(employee_code="EA1", user_id=u.id)
    a = make_project(code="EV-3A")
    b = make_project(code="EV-3B")
    clean = make_project(code="EV-3C")
    for p in (a, b, clean):
        make_project_member(project_id=p.id, employee_id=emp.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(clean.id)])
    )
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=leave_day, tasks=[_task(a.id), _task(b.id, 60)])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) is None


# ---------- multi-day and stale evidence ------------------------------------

def test_multi_day_leave_routes_from_its_start_date_alone(
    db, make_user, make_employee, make_project, make_project_member,
):
    """A 3-day leave does not need a report for every day it covers. One
    reliable project at the boundary routes the whole request."""
    u = make_user("multi@x.com")
    emp = make_employee(employee_code="EM1", user_id=u.id)
    project = make_project(code="MD-1")
    make_project_member(project_id=project.id, employee_id=emp.id)
    leave_start, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    # start .. start+2, with no report on any of the leave days themselves.
    assert routing.resolve_routed_project(db, emp.id, leave_start) == project.id


def test_a_stale_report_does_not_establish_a_project(
    db, make_user, make_employee, make_project, make_project_member,
):
    """The employee's latest report is two working days before the leave. The
    project cannot be established AT THE BOUNDARY, so it is the PM's - there is
    deliberately no N-day window that would let older evidence back in."""
    u = make_user("stale@x.com")
    emp = make_employee(employee_code="ES2", user_id=u.id)
    project = make_project(code="ST-1")
    make_project_member(project_id=project.id, employee_id=emp.id)
    leave_day, _skipped, stale_day = _working_days_back(db, 3)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=stale_day, tasks=[_task(project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) is None


def test_a_far_future_leave_does_not_establish_a_project(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Leave filed weeks out. Neither evidence date has a report, so the PM
    decides it however recent the employee's last report was."""
    u = make_user("future@x.com")
    emp = make_employee(employee_code="ES3", user_id=u.id)
    project = make_project(code="ST-2")
    make_project_member(project_id=project.id, employee_id=emp.id)
    (recent_day,) = _working_days_back(db, 1)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=recent_day, tasks=[_task(project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, recent_day + timedelta(days=18)) is None


# ---------- unresolvable evidence -------------------------------------------

def test_resolve_routed_project_no_report_falls_back(db, make_user, make_employee):
    u = make_user("emp4@x.com")
    emp = make_employee(employee_code="E4", user_id=u.id)
    (leave_day,) = _working_days_back(db, 1)

    assert routing.resolve_routed_project(db, emp.id, leave_day) is None


def test_resolve_routed_project_no_tasks_falls_back(db, make_user, make_employee):
    """A no-activity day (leave/holiday/week-off) legitimately has zero task
    rows - that's a real state, not an error, and must fall back cleanly.
    `day_status` must be one of NO_ACTIVITY_DAY_STATUSES (e.g. week_off) or
    `create_work_report` itself rejects an empty-task report as invalid."""
    from app.modules.work_reports.models import DayStatus

    u = make_user("emp5@x.com")
    emp = make_employee(employee_code="E5", user_id=u.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, day_status=DayStatus.week_off, tasks=[])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) is None


def test_resolve_routed_project_ambiguous_falls_back(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Two distinct projects on the same day - do not guess, fall back."""
    u = make_user("emp6@x.com")
    emp = make_employee(employee_code="E6", user_id=u.id)
    project_a = make_project(code="P-6A")
    project_b = make_project(code="P-6B")
    make_project_member(project_id=project_a.id, employee_id=emp.id)
    make_project_member(project_id=project_b.id, employee_id=emp.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(
            report_date=prev_day, tasks=[_task(project_a.id), _task(project_b.id, 60)]
        )
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) is None


# ---------- a Project Head's own leave --------------------------------------

def test_a_project_head_never_routes_to_a_project(
    db, make_user, make_employee, make_project, make_project_member,
):
    """The requester Heads project A and their report says project B. Their leave
    must NOT route to B's Head - a Head's own leave is the PM's to decide, and a
    NULL routed project is what makes `_assert_can_review` land there."""
    u = make_user("headself@x.com")
    head = make_employee(employee_code="EH1", user_id=u.id)
    own_project = make_project(code="HD-1", head_employee_id=head.id)
    other_project = make_project(code="HD-2")
    make_project_member(project_id=other_project.id, employee_id=head.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(other_project.id)])
    )

    assert own_project.head_employee_id == head.id
    assert routing.resolve_routed_project(db, head.id, leave_day) is None


def test_a_head_of_a_deleted_project_routes_normally(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Heading nothing but an archived project is not being a Head any more, so
    the ordinary work-report evidence applies again."""
    from datetime import datetime, timezone

    u = make_user("headgone@x.com")
    head = make_employee(employee_code="EH2", user_id=u.id)
    dead_project = make_project(code="HD-3", head_employee_id=head.id)
    live_project = make_project(code="HD-4")
    make_project_member(project_id=live_project.id, employee_id=head.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(live_project.id)])
    )

    dead_project.deleted_at = datetime.now(timezone.utc)
    db.add(dead_project)
    db.commit()

    assert routing.resolve_routed_project(db, head.id, leave_day) == live_project.id


def test_a_plain_employee_is_not_treated_as_a_head(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Guard against the Head short-circuit swallowing everybody: an employee who
    is a MEMBER of a headed project still routes to that project's Head."""
    hu = make_user("realhead@x.com")
    head = make_employee(employee_code="EH3", user_id=hu.id)
    project = make_project(code="HD-5", head_employee_id=head.id)

    u = make_user("member@x.com")
    emp = make_employee(employee_code="EH4", user_id=u.id)
    make_project_member(project_id=project.id, employee_id=emp.id)
    leave_day, prev_day = _working_days_back(db, 2)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=prev_day, tasks=[_task(project.id)])
    )

    assert routing.resolve_routed_project(db, emp.id, leave_day) == project.id
