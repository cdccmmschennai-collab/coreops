"""Phase 2 Task 4 — the assigned Head is honored in report review, project +
timeline visibility, and notification routing (Head -> reporting_pm_id ->
project_managers). No activity-assignment logic is involved yet.
"""
from datetime import date

from sqlalchemy import text

from app.modules.activity_requests.service import _pm_user_ids
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.models import WorkReportStatus
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportReject,
    WorkReportTaskIn,
)

TODAY = date.today()
BASE = "/api/v1/projects"


# ---- report review --------------------------------------------------------
def test_head_can_review_report(db, make_user, make_employee, make_project, make_project_member):
    author_u = make_user("author@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-1", user_id=author_u.id)
    project = make_project(code="HR-1", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)

    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)

    head_u = make_user("head@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-1", user_id=head_u.id)
    pm_u = make_user("pm@x.com", role=UserRole.project_manager)
    proj_svc.set_project_head(db, pm_u, project.id, head_e.id)

    out = wr_svc.reject_work_report(db, head_u, report.id, WorkReportReject(review_note="fix"))
    assert out.status == WorkReportStatus.rejected
    assert out.can_review is True


# ---- visibility -----------------------------------------------------------
def test_head_can_view_project_and_timeline(
    client, auth_header, make_project, make_employee, make_user, login
):
    pm = auth_header("pm2@x.com", role=UserRole.project_manager)
    project = make_project(code="HV-1")
    head_u = make_user("hv@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HVE-1", user_id=head_u.id)
    client.put(f"{BASE}/{project.id}/head", headers=pm, json={"head_employee_id": str(head_e.id)})

    head_hdr = login("hv@x.com")
    assert client.get(f"{BASE}/{project.id}", headers=head_hdr).status_code == 200
    assert client.get(f"{BASE}/{project.id}/timeline", headers=head_hdr).status_code == 200


# ---- Task 5: timeline visible to any project member (not just team leads) ---
def test_plain_member_can_view_timeline(
    client, make_project, make_employee, make_user, make_project_member, login
):
    project = make_project(code="TV-2")
    member_u = make_user("member@x.com", role=UserRole.employee)
    member_e = make_employee(employee_code="TVM-1", user_id=member_u.id)
    # a plain contributor membership row (NOT team_lead)
    make_project_member(project_id=project.id, employee_id=member_e.id)

    member_hdr = login("member@x.com")
    assert client.get(f"{BASE}/{project.id}/timeline", headers=member_hdr).status_code == 200


def test_non_member_cannot_view_timeline(
    client, make_project, make_employee, make_user, login
):
    project = make_project(code="TV-3")
    outsider_u = make_user("outsider@x.com", role=UserRole.employee)
    make_employee(employee_code="TVO-1", user_id=outsider_u.id)

    outsider_hdr = login("outsider@x.com")
    assert client.get(f"{BASE}/{project.id}/timeline", headers=outsider_hdr).status_code == 403


# ---- notification routing (Head -> reporting_pm_id -> project_managers) ----
def test_routing_prefers_head(db, make_user, make_employee, make_project):
    head_u = make_user("h@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="RH-1", user_id=head_u.id)
    project = make_project(code="RT-1")
    project.head_employee_id = head_e.id
    db.add(project)
    db.commit()

    rep_pm = make_user("rp@x.com", role=UserRole.project_manager)
    author_e = make_employee(employee_code="RA-1")
    author_e.reporting_pm_id = rep_pm.id  # must NOT win over the Head
    db.add(author_e)
    db.commit()

    assert _pm_user_ids(db, project.id, author_e) == [head_u.id]


def test_routing_falls_back_to_reporting_pm_when_no_head(db, make_user, make_employee, make_project):
    project = make_project(code="RT-2")  # no head
    rep_pm = make_user("rp2@x.com", role=UserRole.project_manager)
    author_e = make_employee(employee_code="RA-2")
    author_e.reporting_pm_id = rep_pm.id
    db.add(author_e)
    db.commit()

    assert _pm_user_ids(db, project.id, author_e) == [rep_pm.id]


def test_routing_falls_back_to_project_managers_last(db, make_user, make_employee, make_project):
    project = make_project(code="RT-3")  # no head
    pm_u = make_user("pm3@x.com", role=UserRole.project_manager)
    # Raw insert: the ProjectManager ORM model carries an updated_at (TimestampMixin)
    # that the deprecated project_managers table lacks. Prod only SELECTs this table.
    db.execute(
        text("INSERT INTO project_managers (project_id, user_id) VALUES (:p, :u)"),
        {"p": str(project.id), "u": str(pm_u.id)},
    )
    db.commit()
    author_e = make_employee(employee_code="RA-3")  # no reporting_pm

    assert _pm_user_ids(db, project.id, author_e) == [pm_u.id]
