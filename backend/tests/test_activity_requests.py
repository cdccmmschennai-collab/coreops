"""Service-level tests for the second-activity approval workflow.

An employee logs one activity, requests a second; the PM approves → the second
becomes a real activity row in the same report. Rejection and dismissal (delete)
round out the lifecycle. Mirrors the direct-service style of
test_work_reports_service.py (no router round-trip needed).
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.modules.activity_master.models import (
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.activity_requests import service as ar_svc
from app.modules.activity_requests.models import ActivityRequest, ActivityRequestStatus
from app.modules.activity_requests.schemas import ActivityRequestCreate
from app.modules.employees.models import Employee
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


def test_activity_request_notifies_pm_not_head(
    db, make_user, make_employee, make_project, make_project_member, sub_activity
):
    """The activity-request notification targets the PM (who reviews it on the
    home-page request bar), never the project Head (who cannot act on it)."""
    from app.modules.notifications.models import Notification

    pm_u = make_user("pm2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PM-2", user_id=pm_u.id)
    head_u = make_user("head2@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HEAD-2", user_id=head_u.id)
    emp_u = make_user("emp2@x.com", role=UserRole.employee)
    emp_e = make_employee(employee_code="E-2", user_id=emp_u.id)
    # The employee reports to the PM; the project has a (different) Head.
    emp_e.reporting_pm_id = pm_u.id
    project = make_project(code="P-2", status=ProjectStatus.active)
    project.head_employee_id = head_e.id
    db.add_all([emp_e, project])
    db.commit()
    make_project_member(project_id=project.id, employee_id=emp_e.id)

    report = wr_svc.create_work_report(
        db, emp_u,
        WorkReportCreate(
            report_date=TODAY,
            tasks=[WorkReportTaskIn(project_id=project.id, description="a", minutes_spent=60)],
        ),
    )
    ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )

    recipients = set(db.execute(select(Notification.user_id)).scalars().all())
    assert pm_u.id in recipients          # PM is notified
    assert head_u.id not in recipients    # Head is NOT notified


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


def test_counts_default_to_zero(db, scenario, sub_activity):
    """A request created without explicit counts defaults every count to 0, and
    the approved activity row inherits those zeros."""
    pm_u, emp_u, project, report = scenario
    req = ar_svc.create_request(
        db,
        emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    assert (req.tags_count, req.docs_count, req.bom_count, req.spares_count) == (0, 0, 0, 0)

    ar_svc.approve_request(db, pm_u, req.id)
    new_row = db.execute(
        select(WorkReportTask).where(
            WorkReportTask.report_id == report.id,
            WorkReportTask.sub_activity_id == sub_activity.id,
        )
    ).scalar_one()
    assert (
        new_row.tags_count,
        new_row.docs_count,
        new_row.bom_count,
        new_row.spares_count,
    ) == (0, 0, 0, 0)


def test_model_does_not_map_task_id(db, scenario, sub_activity):
    """task_id decision: the stale Tasks-module link is no longer mapped, so it
    is never emitted in SELECTs (which broke against production, where the column
    never existed). A request still round-trips end to end without it."""
    from app.modules.activity_requests.models import ActivityRequest

    assert not hasattr(ActivityRequest, "task_id")
    assert "task_id" not in ActivityRequest.__table__.columns

    pm_u, emp_u, project, report = scenario
    req = ar_svc.create_request(
        db,
        emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    # Read back through the ORM (the path that previously errored on task_id).
    assert ar_svc.list_requests(db, pm_u)[0].id == req.id


# ── one-pending-per-employee/report guard (index + service) ───────────────────

def _employee_of(db, user):
    return db.execute(
        select(Employee).where(Employee.user_id == user.id)
    ).scalar_one()


def test_different_reports_each_allow_a_pending_request(db, scenario, sub_activity):
    """The guard is per employee/report: the same employee may hold a pending
    request on two different reports simultaneously."""
    _pm_u, emp_u, project, report = scenario
    report2 = wr_svc.create_work_report(
        db,
        emp_u,
        WorkReportCreate(
            report_date=TODAY - timedelta(days=1),
            tasks=[WorkReportTaskIn(project_id=project.id, description="b", minutes_spent=60)],
        ),
    )

    r1 = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    r2 = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report2.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    assert r1.status == ActivityRequestStatus.pending.value
    assert r2.status == ActivityRequestStatus.pending.value


def test_rejected_request_does_not_block_a_new_pending(db, scenario, sub_activity):
    """A rejected request is not pending, so it never blocks a fresh request for
    the same report."""
    pm_u, emp_u, project, report = scenario
    req = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    ar_svc.reject_request(db, pm_u, req.id)
    # A new pending request is allowed (index only constrains status='pending').
    again = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    assert again.status == ActivityRequestStatus.pending.value


def test_approved_request_does_not_block_a_new_pending(db, scenario, sub_activity):
    """An approved request has become a real activity row and is no longer
    pending, so it does not block another request for the same report."""
    pm_u, emp_u, project, report = scenario
    req = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    ar_svc.approve_request(db, pm_u, req.id)
    again = ar_svc.create_request(
        db, emp_u,
        ActivityRequestCreate(
            report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
        ),
    )
    assert again.status == ActivityRequestStatus.pending.value


def test_duplicate_pending_insert_violates_unique_index(db, scenario, sub_activity):
    """The partial unique index is the authoritative guard: two pending rows for
    the same (employee, report) cannot coexist at the database level."""
    _pm_u, emp_u, _project, report = scenario
    emp = _employee_of(db, emp_u)
    for _ in range(2):
        db.add(
            ActivityRequest(
                employee_id=emp.id,
                report_id=report.id,
                project_id=_project.id,
                sub_activity_id=sub_activity.id,
                status=ActivityRequestStatus.pending.value,
            )
        )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_legacy_null_report_id_rows_are_not_constrained(db, scenario, sub_activity):
    """The index is scoped to report_id IS NOT NULL, so legacy rows (report_id
    NULL, pre-0051) never collide - two such pending rows coexist."""
    _pm_u, emp_u, _project, _report = scenario
    emp = _employee_of(db, emp_u)
    for _ in range(2):
        db.add(
            ActivityRequest(
                employee_id=emp.id,
                report_id=None,
                project_id=_project.id,
                sub_activity_id=sub_activity.id,
                status=ActivityRequestStatus.pending.value,
            )
        )
    db.commit()  # must NOT raise
    count = db.execute(
        select(func.count()).select_from(ActivityRequest).where(
            ActivityRequest.employee_id == emp.id,
            ActivityRequest.report_id.is_(None),
        )
    ).scalar_one()
    assert count == 2


def test_concurrent_create_conflict_maps_to_422_not_500(
    db, scenario, sub_activity, monkeypatch
):
    """A race the pre-check loses (a concurrent pending request already exists
    when the INSERT commits) must surface as the normal 422 business validation
    response, not a 500. We simulate the lost race by disabling the pre-check so
    the code path reaches the INSERT and hits the unique index."""
    _pm_u, emp_u, project, report = scenario
    emp = _employee_of(db, emp_u)
    # An already-committed pending request the pre-check will be made to "miss".
    db.add(
        ActivityRequest(
            employee_id=emp.id,
            report_id=report.id,
            project_id=project.id,
            sub_activity_id=sub_activity.id,
            status=ActivityRequestStatus.pending.value,
        )
    )
    db.commit()

    monkeypatch.setattr(ar_svc, "_has_pending_request", lambda *a, **k: False)

    with pytest.raises(AppError) as ei:
        ar_svc.create_request(
            db, emp_u,
            ActivityRequestCreate(
                report_id=report.id, project_id=project.id, sub_activity_id=sub_activity.id
            ),
        )
    assert ei.value.status_code == 422
    assert ei.value.code == "validation_error"
