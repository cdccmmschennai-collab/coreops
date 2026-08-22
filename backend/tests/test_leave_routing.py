"""Tests for leave-approval routing to Project Head (Phase 1).

`test_leave_routing.py` covers the resolver (Task 2) and this file's own
Task-1 smoke test that `routed_project_id` persists and serializes. Task 3/4
API-level behavior (notification target, scope, authorization) lives in
`test_leave_api.py` alongside the rest of the leave RBAC suite it extends.
"""
from datetime import date, timedelta

from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.leave import routing
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn


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


def _task(project_id, minutes=120):
    return WorkReportTaskIn(project_id=project_id, description="work", minutes_spent=minutes)


def _next_monday(from_date: date) -> date:
    return from_date + timedelta(days=(7 - from_date.weekday()) % 7 or 7)


def test_resolve_routed_project_single_project(
    db, make_user, make_employee, make_project, make_project_member,
):
    u = make_user("emp2@x.com")
    emp = make_employee(employee_code="E2", user_id=u.id)
    project = make_project(code="P-2")
    make_project_member(project_id=project.id, employee_id=emp.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)  # previous working day before a Monday

    wr_svc.create_work_report(db, u, WorkReportCreate(report_date=friday, tasks=[_task(project.id)]))

    resolved = routing.resolve_routed_project(db, emp.id, monday)
    assert resolved == project.id


def test_resolve_routed_project_skips_weekend(
    db, make_user, make_employee, make_project, make_project_member,
):
    """Monday's leave routes off Friday's report - Sat/Sun are never checked,
    proving previous_working_day (not a naive `date - 1`) drives the lookup."""
    u = make_user("emp3@x.com")
    emp = make_employee(employee_code="E3", user_id=u.id)
    project = make_project(code="P-3")
    make_project_member(project_id=project.id, employee_id=emp.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(db, u, WorkReportCreate(report_date=friday, tasks=[_task(project.id)]))
    # A Saturday report must NOT be picked over Friday's - previous_working_day
    # never lands on a weekend, so create one and confirm it's ignored.
    other_project = make_project(code="P-3B")
    make_project_member(project_id=other_project.id, employee_id=emp.id)
    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday + timedelta(days=1), tasks=[_task(other_project.id)])
    )

    resolved = routing.resolve_routed_project(db, emp.id, monday)
    assert resolved == project.id


def test_resolve_routed_project_no_report_falls_back(db, make_user, make_employee):
    u = make_user("emp4@x.com")
    emp = make_employee(employee_code="E4", user_id=u.id)
    monday = _next_monday(date.today())

    assert routing.resolve_routed_project(db, emp.id, monday) is None


def test_resolve_routed_project_no_tasks_falls_back(db, make_user, make_employee):
    """A no-activity day (leave/holiday/week-off) legitimately has zero task
    rows - that's a real state, not an error, and must fall back cleanly.
    `day_status` must be one of NO_ACTIVITY_DAY_STATUSES (e.g. week_off) or
    `create_work_report` itself rejects an empty-task report as invalid."""
    from app.modules.work_reports.models import DayStatus

    u = make_user("emp5@x.com")
    emp = make_employee(employee_code="E5", user_id=u.id)
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, day_status=DayStatus.week_off, tasks=[])
    )

    assert routing.resolve_routed_project(db, emp.id, monday) is None


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
    monday = _next_monday(date.today())
    friday = monday - timedelta(days=3)

    wr_svc.create_work_report(
        db, u, WorkReportCreate(report_date=friday, tasks=[_task(project_a.id), _task(project_b.id, 60)])
    )

    assert routing.resolve_routed_project(db, emp.id, monday) is None
