"""Service-level unit tests for Daily Work Reports (Phase B4).

Routers do not exist yet; these call the service functions directly with the `db`
fixture and constructed actors. Covers workflow transitions, validation rules
(§6) and RBAC scoping (§3) from DAILY_WORK_REPORTS_SPEC.md.
"""
from datetime import date, timedelta

import pytest

from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports import service as svc
from app.modules.work_reports.models import WorkReportStatus
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportEditRequest,
    WorkReportReject,
    WorkReportTaskIn,
    WorkReportUpdate,
)
from app.shared.errors import AppError

TODAY = date.today()


def _task(project_id, minutes=60, desc="work"):
    return WorkReportTaskIn(project_id=project_id, description=desc, minutes_spent=minutes)


@pytest.fixture()
def author(make_user, make_employee, make_project, make_project_member):
    """Factory: a user with an employee profile, a project, and membership in it."""

    def _make(
        *,
        email,
        code,
        role=UserRole.employee,
        manager_id=None,
        proj_code,
        proj_status=ProjectStatus.active,
        member=True,
    ):
        u = make_user(email, role=role)
        e = make_employee(employee_code=code, user_id=u.id, manager_id=manager_id)
        p = make_project(code=proj_code, status=proj_status)
        if member:
            make_project_member(project_id=p.id, employee_id=e.id)
        return u, e, p

    return _make


# ---------- workflow transitions -------------------------------------------
def test_transition_draft_to_submitted(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id, 120)]))
    assert r.status == WorkReportStatus.draft
    assert r.total_minutes == 120

    r = svc.submit_work_report(db, u, r.id)
    assert r.status == WorkReportStatus.submitted
    assert r.submitted_at is not None


def test_transition_submitted_to_approved(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)

    r = svc.approve_work_report(db, admin, r.id)
    assert r.status == WorkReportStatus.approved
    assert r.reviewed_by == admin.id
    assert r.reviewed_at is not None


def test_transition_submitted_to_rejected(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)

    r = svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="Add detail"))
    assert r.status == WorkReportStatus.rejected
    assert r.review_note == "Add detail"
    assert r.reviewed_by == admin.id


def test_transition_rejected_to_submitted(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="redo"))

    r = svc.submit_work_report(db, u, r.id)
    assert r.status == WorkReportStatus.submitted
    assert r.review_note is None  # cleared on resubmission


def test_invalid_transition_approve_draft_is_422(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    with pytest.raises(AppError) as ei:
        svc.approve_work_report(db, admin, r.id)
    assert ei.value.status_code == 422


def test_edit_rejected_returns_to_draft(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="redo"))

    r = svc.update_work_report(db, u, r.id, WorkReportUpdate(tasks=[_task(p.id, 90)]))
    assert r.status == WorkReportStatus.draft
    assert r.total_minutes == 90
    assert r.review_note is None


def test_pm_list_scope_includes_rejected_and_granted(db, author, make_user):
    """A rejected/granted report must stay visible to the reviewer who acted
    on it — disappearing the moment it leaves 'submitted' would make it
    impossible to track what's been sent back or reopened."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.project_manager)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="redo"))

    _, total = svc.list_work_reports(
        db, admin, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    assert total == 1

    svc.submit_work_report(db, u, r.id)
    svc.request_edit_work_report(db, u, r.id, WorkReportEditRequest(note="need to fix a typo"))
    svc.grant_edit_work_report(db, admin, r.id)

    _, total = svc.list_work_reports(
        db, admin, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    assert total == 1


def test_team_lead_list_scope_includes_rejected_and_granted(
    db, author, make_user, make_employee, make_project_member
):
    from app.modules.projects.models import ProjectMemberRole

    lead_u, lead_e, p = author(email="lead@x.com", code="TL-1", proj_code="P-1", member=False)
    make_project_member(project_id=p.id, employee_id=lead_e.id, role=ProjectMemberRole.team_lead)
    emp_u, emp_e, _ = author(email="e@x.com", code="E-1", proj_code="P-2", member=False)
    make_project_member(project_id=p.id, employee_id=emp_e.id, role=ProjectMemberRole.contributor)

    r = svc.create_work_report(db, emp_u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, emp_u, r.id)
    svc.reject_work_report(db, lead_u, r.id, WorkReportReject(review_note="redo"))

    _, total = svc.list_work_reports(
        db, lead_u, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    assert total == 1


# ---------- validation rules (§6) ------------------------------------------
def test_duplicate_employee_date_409(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    with pytest.raises(AppError) as ei:
        svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert ei.value.status_code == 409


def test_future_date_422(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    with pytest.raises(AppError) as ei:
        svc.create_work_report(
            db, u, WorkReportCreate(report_date=TODAY + timedelta(days=1), tasks=[_task(p.id)])
        )
    assert ei.value.status_code == 422


def test_total_minutes_over_1440_422(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    with pytest.raises(AppError) as ei:
        svc.create_work_report(
            db,
            u,
            WorkReportCreate(report_date=TODAY, tasks=[_task(p.id, 800), _task(p.id, 700)]),
        )
    assert ei.value.status_code == 422


def test_total_minutes_skips_null_tasks(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    tasks = [
        WorkReportTaskIn(project_id=p.id, description="timed", minutes_spent=60),
        WorkReportTaskIn(project_id=p.id, description="no time", minutes_spent=None),
    ]
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=tasks))
    assert r.total_minutes == 60  # null task minutes not counted


def test_create_with_day_status_and_location_persists(db, author):
    from app.modules.work_reports.models import DayStatus, WorkLocation
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    create = WorkReportCreate(
        report_date=TODAY,
        day_status=DayStatus.work_from_home,
        location=WorkLocation.chennai,
        remarks="WFH today",
        tasks=[_task(p.id)],
    )
    r = svc.create_work_report(db, u, create)
    assert r.day_status == DayStatus.work_from_home
    assert r.location == WorkLocation.chennai
    assert r.remarks == "WFH today"


def test_inactive_project_422(db, author):
    u, e, p = author(
        email="a@x.com", code="E-1", proj_code="P-ARCH", proj_status=ProjectStatus.archived
    )
    with pytest.raises(AppError) as ei:
        svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert ei.value.status_code == 422


def test_non_member_project_422(db, author, make_project):
    """Employees can only log time to projects they are assigned to."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    other = make_project(code="P-OTHER", status=ProjectStatus.active)  # not a member
    with pytest.raises(AppError) as ei:
        svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(other.id)]))
    assert ei.value.status_code == 422


def test_edit_window_violation_422(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    with pytest.raises(AppError) as ei:
        svc.create_work_report(
            db, u, WorkReportCreate(report_date=date(2020, 1, 1), tasks=[_task(p.id)])
        )
    assert ei.value.status_code == 422


def test_create_without_employee_profile_422(db, make_user, make_project):
    """A user with no employee profile cannot author a report."""
    u = make_user("ghost@x.com", role=UserRole.employee)
    p = make_project(code="P-1", status=ProjectStatus.active)
    with pytest.raises(AppError) as ei:
        svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert ei.value.status_code == 422


# ---------- RBAC: ownership ------------------------------------------------
def test_employee_cannot_read_others_report(db, author):
    a_user, a_emp, a_proj = author(email="a@x.com", code="E-1", proj_code="P-1")
    b_user, b_emp, b_proj = author(email="b@x.com", code="E-2", proj_code="P-2")
    r = svc.create_work_report(db, a_user, WorkReportCreate(report_date=TODAY, tasks=[_task(a_proj.id)]))

    # author can read own
    assert svc.get_work_report(db, a_user, r.id).id == r.id
    # other employee cannot
    with pytest.raises(AppError) as ei:
        svc.get_work_report(db, b_user, r.id)
    assert ei.value.status_code == 403
    # and it is invisible in B's list
    _, total = svc.list_work_reports(
        db, b_user, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    assert total == 0


def test_employee_cannot_review(db, author, make_user, make_employee):
    a_user, a_emp, a_proj = author(email="a@x.com", code="E-1", proj_code="P-1")
    r = svc.create_work_report(db, a_user, WorkReportCreate(report_date=TODAY, tasks=[_task(a_proj.id)]))
    svc.submit_work_report(db, a_user, r.id)

    other = make_user("c@x.com", role=UserRole.employee)
    make_employee(employee_code="E-9", user_id=other.id)
    with pytest.raises(AppError) as ei:
        svc.approve_work_report(db, other, r.id)
    assert ei.value.status_code == 403


def test_non_author_cannot_edit_or_delete(db, author):
    a_user, a_emp, a_proj = author(email="a@x.com", code="E-1", proj_code="P-1")
    b_user, b_emp, b_proj = author(email="b@x.com", code="E-2", proj_code="P-2")
    r = svc.create_work_report(db, a_user, WorkReportCreate(report_date=TODAY, tasks=[_task(a_proj.id)]))
    with pytest.raises(AppError) as ei:
        svc.update_work_report(db, b_user, r.id, WorkReportUpdate(summary="x"))
    assert ei.value.status_code == 403
    with pytest.raises(AppError) as ei:
        svc.delete_work_report(db, b_user, r.id)
    assert ei.value.status_code == 403


def test_delete_non_draft_is_403(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    with pytest.raises(AppError) as ei:
        svc.delete_work_report(db, u, r.id)
    assert ei.value.status_code == 403


def test_edit_submitted_is_403(db, author):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    with pytest.raises(AppError) as ei:
        svc.update_work_report(db, u, r.id, WorkReportUpdate(summary="x"))
    assert ei.value.status_code == 403


# ---------- RBAC: project_manager global access ----------------------------
def test_any_project_manager_can_review_any_report(
    db, make_user, make_employee, make_project, make_project_member
):
    m1 = make_user("m1@x.com", role=UserRole.project_manager)
    m1_emp = make_employee(employee_code="M-1", user_id=m1.id)
    m2 = make_user("m2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="M-2", user_id=m2.id)

    emp_user = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E-1", user_id=emp_user.id, manager_id=m1_emp.id)
    p = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=p.id, employee_id=emp.id)

    r = svc.create_work_report(db, emp_user, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, emp_user, r.id)

    # ANY project_manager can approve (no team scoping)
    approved = svc.approve_work_report(db, m2, r.id)
    assert approved.status == WorkReportStatus.approved


def test_project_manager_list_scope_sees_all(
    db, make_user, make_employee, make_project, make_project_member
):
    m1 = make_user("m1@x.com", role=UserRole.project_manager)
    m1_emp = make_employee(employee_code="M-1", user_id=m1.id)
    emp_user = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E-1", user_id=emp_user.id, manager_id=m1_emp.id)
    outsider = make_user("o@x.com", role=UserRole.employee)
    out_emp = make_employee(employee_code="E-2", user_id=outsider.id)

    p = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=p.id, employee_id=emp.id)
    p2 = make_project(code="P-2", status=ProjectStatus.active)
    make_project_member(project_id=p2.id, employee_id=out_emp.id)

    svc.create_work_report(db, emp_user, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.create_work_report(db, outsider, WorkReportCreate(report_date=TODAY, tasks=[_task(p2.id)]))

    _, total = svc.list_work_reports(
        db, m1, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    # project_manager sees ALL reports (no team scope)
    assert total == 2


# ---------- RBAC: admin ----------------------------------------------------
def test_admin_sees_all_and_can_approve(db, author, make_user):
    a_user, a_emp, a_proj = author(email="a@x.com", code="E-1", proj_code="P-1")
    b_user, b_emp, b_proj = author(email="b@x.com", code="E-2", proj_code="P-2")
    admin = make_user("admin@x.com", role=UserRole.project_manager)

    ra = svc.create_work_report(db, a_user, WorkReportCreate(report_date=TODAY, tasks=[_task(a_proj.id)]))
    svc.create_work_report(db, b_user, WorkReportCreate(report_date=TODAY, tasks=[_task(b_proj.id)]))
    svc.submit_work_report(db, a_user, ra.id)

    _, total = svc.list_work_reports(
        db, admin, employee_id=None, project_id=None, status=None,
        date_from=None, date_to=None, limit=50, offset=0,
    )
    assert total == 2
    assert svc.get_work_report(db, admin, ra.id).id == ra.id
    assert svc.approve_work_report(db, admin, ra.id).status == WorkReportStatus.approved


# ── project snapshot tests (migration 0017) ──────────────────────────────────

def test_task_snapshot_populated_on_create(db, author):
    """project_name / project_code / project_job_code_code are snapshotted at create."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="SNAP-1")
    # Give the project a name so we can verify the snapshot
    p.name = "Snapshot Project"
    db.add(p)
    db.commit()

    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert len(r.tasks) == 1
    t = r.tasks[0]
    assert t.project_name == "Snapshot Project"
    assert t.project_code == "SNAP-1"
    assert t.project_job_code_code is None   # no job code linked


def test_task_snapshot_populated_on_update(db, author):
    """Snapshot is refreshed when tasks are replaced via update."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-UPDATE")
    p.name = "Original Name"
    db.add(p); db.commit()

    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    # Rename the project and update the report — snapshot should reflect new name
    p.name = "Renamed Project"
    db.add(p); db.commit()

    r = svc.update_work_report(db, u, r.id, WorkReportUpdate(tasks=[_task(p.id, 90)]))
    t = r.tasks[0]
    assert t.project_name == "Renamed Project"
    assert t.project_code == "P-UPDATE"
    assert r.total_minutes == 90


def test_task_snapshot_includes_job_code(db, author, db_with_job_code):
    """project_job_code_code is snapshotted from the linked job code."""
    u, e, p, jc = db_with_job_code(
        email="a@x.com", code="E-1", proj_code="JC-1", jc_code="J-001"
    )
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert r.tasks[0].project_job_code_code == "J-001"


def test_snapshot_survives_project_rename(db, author):
    """Snapshot does NOT change when the project is renamed after saving."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-RENAME")
    p.name = "Original Name"
    db.add(p); db.commit()

    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    assert r.tasks[0].project_name == "Original Name"

    # Rename after save — existing report must be unaffected
    p.name = "Renamed After Save"
    db.add(p); db.commit()

    reloaded = svc.get_work_report(db, u, r.id)
    assert reloaded.tasks[0].project_name == "Original Name"   # snapshot unchanged


def test_snapshot_readable_after_project_archived(db, author):
    """Snapshot allows reading project info even when the project is archived."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-ARCH")
    p.name = "Will Be Archived"
    db.add(p); db.commit()

    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))

    # Archive the project after the report is saved
    p.status = ProjectStatus.archived
    db.add(p); db.commit()

    reloaded = svc.get_work_report(db, u, r.id)
    assert reloaded.tasks[0].project_name == "Will Be Archived"
    assert reloaded.tasks[0].project_code == "P-ARCH"


def test_snapshot_readable_after_membership_removed(db, author):
    """Snapshot is readable even after the employee is removed from the project."""
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-MEMBER")
    p.name = "Membership Project"
    db.add(p); db.commit()

    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))

    # Remove the membership
    from sqlalchemy import delete as sa_delete
    from app.modules.projects.models import ProjectMember
    db.execute(sa_delete(ProjectMember).where(ProjectMember.employee_id == e.id))
    db.commit()

    # Employee can still read their own existing report — snapshot intact
    admin = make_user_helper(db, "admin@x.com", role=UserRole.project_manager)
    reloaded = svc.get_work_report(db, admin, r.id)
    assert reloaded.tasks[0].project_name == "Membership Project"


@pytest.fixture()
def db_with_job_code(db, author):
    """Factory: user + employee + project linked to a job code."""
    from app.modules.job_codes.models import JobCode

    def _make(*, email, code, proj_code, jc_code):
        jc = JobCode(code=jc_code, name=f"Job {jc_code}", is_active=True)
        db.add(jc); db.commit(); db.refresh(jc)
        u, e, p = author(email=email, code=code, proj_code=proj_code)
        p.job_code_id = jc.id; db.add(p); db.commit()
        return u, e, p, jc

    return _make


def make_user_helper(db, email, role=UserRole.project_manager):
    from app.core.security import hash_password
    from app.modules.users.models import User
    u = User(email=email, password_hash=hash_password("pw"), role=role, is_active=True)
    db.add(u); db.commit(); db.refresh(u)
    return u
