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
    admin = make_user("admin@x.com", role=UserRole.admin)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)

    r = svc.approve_work_report(db, admin, r.id)
    assert r.status == WorkReportStatus.approved
    assert r.reviewed_by == admin.id
    assert r.reviewed_at is not None


def test_transition_submitted_to_rejected(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.admin)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)

    r = svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="Add detail"))
    assert r.status == WorkReportStatus.rejected
    assert r.review_note == "Add detail"
    assert r.reviewed_by == admin.id


def test_transition_rejected_to_submitted(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.admin)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="redo"))

    r = svc.submit_work_report(db, u, r.id)
    assert r.status == WorkReportStatus.submitted
    assert r.review_note is None  # cleared on resubmission


def test_invalid_transition_approve_draft_is_422(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.admin)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    with pytest.raises(AppError) as ei:
        svc.approve_work_report(db, admin, r.id)
    assert ei.value.status_code == 422


def test_edit_rejected_returns_to_draft(db, author, make_user):
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    admin = make_user("admin@x.com", role=UserRole.admin)
    r = svc.create_work_report(db, u, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, u, r.id)
    svc.reject_work_report(db, admin, r.id, WorkReportReject(review_note="redo"))

    r = svc.update_work_report(db, u, r.id, WorkReportUpdate(tasks=[_task(p.id, 90)]))
    assert r.status == WorkReportStatus.draft
    assert r.total_minutes == 90
    assert r.review_note is None


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
        day_status=DayStatus.wfh,
        location=WorkLocation.chennai,
        remarks="WFH today",
        tasks=[_task(p.id)],
    )
    r = svc.create_work_report(db, u, create)
    assert r.day_status == DayStatus.wfh
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
    u, e, p = author(email="a@x.com", code="E-1", proj_code="P-1")
    other = make_project(code="P-OTHER", status=ProjectStatus.active)  # author not a member
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


# ---------- RBAC: manager team scope ---------------------------------------
def test_manager_reviews_team_but_not_outsiders(
    db, make_user, make_employee, make_project, make_project_member
):
    # manager M1 over employee E; manager M2 unrelated
    m1 = make_user("m1@x.com", role=UserRole.manager)
    m1_emp = make_employee(employee_code="M-1", user_id=m1.id)
    m2 = make_user("m2@x.com", role=UserRole.manager)
    make_employee(employee_code="M-2", user_id=m2.id)

    emp_user = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E-1", user_id=emp_user.id, manager_id=m1_emp.id)
    p = make_project(code="P-1", status=ProjectStatus.active)
    make_project_member(project_id=p.id, employee_id=emp.id)

    r = svc.create_work_report(db, emp_user, WorkReportCreate(report_date=TODAY, tasks=[_task(p.id)]))
    svc.submit_work_report(db, emp_user, r.id)

    # M2 (not the manager) cannot approve
    with pytest.raises(AppError) as ei:
        svc.approve_work_report(db, m2, r.id)
    assert ei.value.status_code == 403

    # M1 (direct manager) can approve
    approved = svc.approve_work_report(db, m1, r.id)
    assert approved.status == WorkReportStatus.approved


def test_manager_list_scope_includes_team(
    db, make_user, make_employee, make_project, make_project_member
):
    m1 = make_user("m1@x.com", role=UserRole.manager)
    m1_emp = make_employee(employee_code="M-1", user_id=m1.id)
    emp_user = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E-1", user_id=emp_user.id, manager_id=m1_emp.id)
    outsider = make_user("o@x.com", role=UserRole.employee)
    out_emp = make_employee(employee_code="E-2", user_id=outsider.id)  # no manager link

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
    assert total == 1  # only the team member's report, not the outsider's


# ---------- RBAC: admin ----------------------------------------------------
def test_admin_sees_all_and_can_approve(db, author, make_user):
    a_user, a_emp, a_proj = author(email="a@x.com", code="E-1", proj_code="P-1")
    b_user, b_emp, b_proj = author(email="b@x.com", code="E-2", proj_code="P-2")
    admin = make_user("admin@x.com", role=UserRole.admin)

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
