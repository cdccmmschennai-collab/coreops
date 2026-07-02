"""Service-level tests for the second-activity approval workflow.

An employee logs one activity, requests a second; the PM approves → the second
becomes a real activity row in the same report. Rejection and dismissal (delete)
round out the lifecycle. Mirrors the direct-service style of
test_work_reports_service.py (no router round-trip needed).
"""
from datetime import date

import pytest
from sqlalchemy import func, select

from app.modules.activity_master.models import (
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.activity_requests import service as ar_svc
from app.modules.activity_requests.models import ActivityRequestStatus
from app.modules.activity_requests.schemas import ActivityRequestCreate
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.models import WorkReportTask
from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn
from app.shared.errors import AppError

TODAY = date.today()


@pytest.fixture()
def sub_activity(db):
    act = ActivityMaster(name="Inspection", level=LEVEL_ACTIVITY)
    db.add(act)
    db.flush()
    sub = ActivityMaster(
        name="Bearing Check",
        level=LEVEL_SUB_ACTIVITY,
        parent_id=act.id,
        benchmark_type="TASK_BASED",
        benchmark_period_days=1,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


@pytest.fixture()
def scenario(db, make_user, make_employee, make_project, make_project_member):
    """A project member (employee) + a PM + a saved report with one activity."""
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM-1", user_id=pm_u.id)

    emp_u = make_user("emp@x.com", role=UserRole.employee)
    emp_e = make_employee(employee_code="E-1", user_id=emp_u.id)
    project = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp_e.id)

    report = wr_svc.create_work_report(
        db,
        emp_u,
        WorkReportCreate(
            report_date=TODAY,
            tasks=[WorkReportTaskIn(project_id=project.id, description="a", minutes_spent=60)],
        ),
    )
    return pm_u, emp_u, project, report


def _task_count(db, report_id):
    return db.execute(
        select(func.count()).select_from(WorkReportTask).where(
            WorkReportTask.report_id == report_id
        )
    ).scalar_one()


def test_approve_creates_second_report_row(db, scenario, sub_activity):
    pm_u, emp_u, project, report = scenario
    assert _task_count(db, report.id) == 1

    req = ar_svc.create_request(
        db,
        emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    assert req.status == ActivityRequestStatus.pending.value
    assert req.report_id == report.id

    approved = ar_svc.approve_request(db, pm_u, req.id)
    assert approved.status == ActivityRequestStatus.approved.value
    # The requested activity is now a real second row in the same report.
    assert _task_count(db, report.id) == 2
    new_row = db.execute(
        select(WorkReportTask).where(
            WorkReportTask.report_id == report.id,
            WorkReportTask.sub_activity_id == sub_activity.id,
        )
    ).scalar_one()
    assert new_row.sub_activity_name == "Bearing Check"


def test_second_pending_request_is_blocked(db, scenario, sub_activity):
    _pm_u, emp_u, project, report = scenario
    ar_svc.create_request(
        db,
        emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    with pytest.raises(AppError):
        ar_svc.create_request(
            db,
            emp_u,
            ActivityRequestCreate(
                report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
            ),
        )


def test_reject_then_dismiss(db, scenario, sub_activity):
    pm_u, emp_u, project, report = scenario
    req = ar_svc.create_request(
        db,
        emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    rejected = ar_svc.reject_request(db, pm_u, req.id)
    assert rejected.status == ActivityRequestStatus.rejected.value
    # No new row is created on rejection.
    assert _task_count(db, report.id) == 1

    # The employee can dismiss their rejected request, then request again.
    ar_svc.delete_request(db, emp_u, req.id)
    mine = ar_svc.list_my_requests(db, emp_u, report.id)
    assert mine == []
