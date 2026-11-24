"""Phase 2 Task 4 — the assigned Head is honored in report review, project +
timeline visibility, and notification routing (Head -> reporting_pm_id ->
project_managers). No activity-assignment logic is involved yet.
"""
from datetime import date

import pytest
from sqlalchemy import text

from app.modules.activity_requests.service import _pm_user_ids
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole
from app.modules.work_reports import service as wr_svc
from app.modules.work_reports.models import WorkReportStatus
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportEditRequest,
    WorkReportTaskIn,
)
from app.shared.errors import AppError

TODAY = date.today()
BASE = "/api/v1/projects"


def _submitted_report_with_head(db, make_user, make_employee, make_project, make_project_member,
                                *, author_email, author_code, head_email, head_code, proj_code,
                                request_edit=True):
    """Create + submit a report, assign a Head, and (optionally) file an edit
    request. Returns (author_u, head_u, report)."""
    author_u = make_user(author_email, role=UserRole.employee)
    author_e = make_employee(employee_code=author_code, user_id=author_u.id)
    project = make_project(code=proj_code, status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)

    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)

    head_u = make_user(head_email, role=UserRole.employee)
    head_e = make_employee(employee_code=head_code, user_id=head_u.id)
    pm_u = make_user(f"pm-{proj_code}@x.com", role=UserRole.project_manager)
    proj_svc.set_project_head(db, pm_u, project.id, head_e.id)

    if request_edit:
        wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))
    return author_u, head_u, report


# ---- report review (edit-request workflow) --------------------------------
def test_head_can_grant_edit(db, make_user, make_employee, make_project, make_project_member):
    _author_u, head_u, report = _submitted_report_with_head(
        db, make_user, make_employee, make_project, make_project_member,
        author_email="author@x.com", author_code="AU-1",
        head_email="head@x.com", head_code="HD-1", proj_code="HR-1",
    )

    out = wr_svc.grant_edit_work_report(db, head_u, report.id)
    assert out.status == WorkReportStatus.granted
    assert out.can_review is True


def test_pm_cannot_grant_edit(db, make_user, make_employee, make_project, make_project_member):
    _author_u, _head_u, report = _submitted_report_with_head(
        db, make_user, make_employee, make_project, make_project_member,
        author_email="author2@x.com", author_code="AU-2",
        head_email="head2@x.com", head_code="HD-2", proj_code="HR-2",
    )

    pm_u = make_user("pm-grant@x.com", role=UserRole.project_manager)
    with pytest.raises(AppError) as ei:
        wr_svc.grant_edit_work_report(db, pm_u, report.id)
    assert ei.value.status_code == 403


def test_edit_request_notifies_head_not_manager(
    db, make_user, make_employee, make_project, make_project_member
):
    """The edit request notifies only the Project Head — never the PM/manager,
    even when the author's manager is a project_manager."""
    mgr_u = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr_e = make_employee(employee_code="MG-1", user_id=mgr_u.id)
    author_u = make_user("author3@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-3", user_id=author_u.id, manager_id=mgr_e.id)
    project = make_project(code="HR-3", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)

    head_u = make_user("head3@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-3", user_id=head_u.id)
    pm_u = make_user("pm-notify@x.com", role=UserRole.project_manager)
    proj_svc.set_project_head(db, pm_u, project.id, head_e.id)

    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))

    def edit_req_count(user_id):
        return db.execute(
            text(
                "SELECT count(*) FROM notifications "
                "WHERE user_id = :uid AND type = 'report_edit_requested'"
            ),
            {"uid": str(user_id)},
        ).scalar_one()

    assert edit_req_count(head_u.id) == 1
    assert edit_req_count(mgr_u.id) == 0


# ---- PM fallback when a project has no Head --------------------------------
def _edit_req_count(db, user_id):
    return db.execute(
        text(
            "SELECT count(*) FROM notifications "
            "WHERE user_id = :uid AND type = 'report_edit_requested'"
        ),
        {"uid": str(user_id)},
    ).scalar_one()


def _headless_report(db, make_user, make_employee, make_project, make_project_member, *, tag):
    """Submitted report on a project with NO Head, author has a reporting PM,
    edit request filed. Returns (author_u, rep_pm, project, report)."""
    rep_pm = make_user(f"rpm-{tag}@x.com", role=UserRole.project_manager)
    author_u = make_user(f"author-{tag}@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code=f"AU-{tag}", user_id=author_u.id,
                             reporting_pm_id=rep_pm.id)
    project = make_project(code=f"NH-{tag}", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)
    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))
    return author_u, rep_pm, project, report


def test_no_head_edit_request_notifies_reporting_pm(
    db, make_user, make_employee, make_project, make_project_member
):
    _a, rep_pm, _p, _r = _headless_report(
        db, make_user, make_employee, make_project, make_project_member, tag="F1")
    assert _edit_req_count(db, rep_pm.id) == 1


def test_no_head_only_reporting_pm_notified_not_other_pms(
    db, make_user, make_employee, make_project, make_project_member
):
    other_pm = make_user("other-pm-f5@x.com", role=UserRole.project_manager)
    _a, rep_pm, _p, _r = _headless_report(
        db, make_user, make_employee, make_project, make_project_member, tag="F5")
    assert _edit_req_count(db, rep_pm.id) == 1
    assert _edit_req_count(db, other_pm.id) == 0


def test_no_head_no_reporting_pm_notifies_all_pms(
    db, make_user, make_employee, make_project, make_project_member
):
    pm_a = make_user("pm-a-f6@x.com", role=UserRole.project_manager)
    pm_b = make_user("pm-b-f6@x.com", role=UserRole.project_manager)
    author_u = make_user("author-f6@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-F6", user_id=author_u.id)  # no reporting PM
    project = make_project(code="NH-F6", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)
    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))

    assert _edit_req_count(db, pm_a.id) == 1
    assert _edit_req_count(db, pm_b.id) == 1


def test_no_head_pm_can_grant_edit(
    db, make_user, make_employee, make_project, make_project_member
):
    _a, rep_pm, _p, report = _headless_report(
        db, make_user, make_employee, make_project, make_project_member, tag="F2")
    assert wr_svc.get_work_report(db, rep_pm, report.id).can_review is True
    out = wr_svc.grant_edit_work_report(db, rep_pm, report.id)
    assert out.status == WorkReportStatus.granted


def test_head_removed_hands_pending_request_to_pm(
    db, make_user, make_employee, make_project, make_project_member
):
    """Authority is live: clearing the Head lets a PM grant a request that was
    filed while the Head was assigned."""
    _author_u, _head_u, report = _submitted_report_with_head(
        db, make_user, make_employee, make_project, make_project_member,
        author_email="author-f3@x.com", author_code="AU-F3",
        head_email="head-f3@x.com", head_code="HD-F3", proj_code="HR-F3",
    )
    pm_u = make_user("pm-f3@x.com", role=UserRole.project_manager)
    with pytest.raises(AppError):
        wr_svc.grant_edit_work_report(db, pm_u, report.id)

    project_id = report.tasks[0].project_id
    proj_svc.set_project_head(db, pm_u, project_id, None)
    out = wr_svc.grant_edit_work_report(db, pm_u, report.id)
    assert out.status == WorkReportStatus.granted


def test_head_assigned_pm_not_notified(
    db, make_user, make_employee, make_project, make_project_member
):
    """With a Head assigned the reporting PM is not notified (Head-only)."""
    rep_pm = make_user("rpm-f4@x.com", role=UserRole.project_manager)
    author_u = make_user("author-f4@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-F4", user_id=author_u.id,
                             reporting_pm_id=rep_pm.id)
    project = make_project(code="HR-F4", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)
    head_u = make_user("head-f4@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-F4", user_id=head_u.id)
    proj_svc.set_project_head(db, rep_pm, project.id, head_e.id)

    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))

    assert _edit_req_count(db, head_u.id) == 1
    assert _edit_req_count(db, rep_pm.id) == 0


# ---- edit_reviewers: who the pending request is waiting on ------------------
def test_edit_reviewers_names_head_and_follows_head_change(
    db, make_user, make_employee, make_project, make_project_member
):
    author_u, _head_u, report = _submitted_report_with_head(
        db, make_user, make_employee, make_project, make_project_member,
        author_email="author-r1@x.com", author_code="AU-R1",
        head_email="head-r1@x.com", head_code="HD-R1", proj_code="HR-R1",
    )
    out = wr_svc.get_work_report(db, author_u, report.id)
    assert [r["role"] for r in out.edit_reviewers] == ["head"]

    new_head_u = make_user("head2-r1@x.com", role=UserRole.employee)
    new_head = make_employee(employee_code="HD-R1B", user_id=new_head_u.id,
                             first_name="New", last_name="Head")
    pm_u = make_user("pm-r1@x.com", role=UserRole.project_manager)
    proj_svc.set_project_head(db, pm_u, report.tasks[0].project_id, new_head.id)

    out = wr_svc.get_work_report(db, author_u, report.id)
    assert out.edit_reviewers == [{"role": "head", "name": "New Head"}]


def test_edit_reviewers_no_head_names_reporting_pm(
    db, make_user, make_employee, make_project, make_project_member
):
    author_u, rep_pm, _p, report = _headless_report(
        db, make_user, make_employee, make_project, make_project_member, tag="R2")
    make_employee(employee_code="PM-R2", user_id=rep_pm.id, first_name="Alex", last_name="Manager")
    out = wr_svc.get_work_report(db, author_u, report.id)
    assert out.edit_reviewers == [{"role": "reporting_pm", "name": "Alex Manager"}]


def test_edit_reviewers_no_head_no_reporting_pm_is_empty(
    db, make_user, make_employee, make_project, make_project_member
):
    make_user("pm-r3@x.com", role=UserRole.project_manager)
    author_u = make_user("author-r3@x.com", role=UserRole.employee)
    author_e = make_employee(employee_code="AU-R3", user_id=author_u.id)
    project = make_project(code="NH-R3", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=author_e.id)
    report = wr_svc.create_work_report(db, author_u, WorkReportCreate(
        report_date=TODAY,
        tasks=[WorkReportTaskIn(project_id=project.id, description="w", minutes_spent=60)],
    ))
    wr_svc.submit_work_report(db, author_u, report.id)
    wr_svc.request_edit_work_report(db, author_u, report.id, WorkReportEditRequest(note="fix"))

    assert wr_svc.get_work_report(db, author_u, report.id).edit_reviewers == []


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


# ---- activity-request routing (reporting_pm_id -> project_managers; Head excluded) ----
def test_routing_prefers_pm_not_head(db, make_user, make_employee, make_project):
    """Approved behavior: a second-activity request routes to the responsible PM
    (the employee's reporting PM), NEVER the Project Head. Reviewing an activity
    request (approve/reject) is PM-only, so routing it to the Head - who cannot
    act on it - was noise. Even with a Head assigned, the reporting PM wins."""
    head_u = make_user("h@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="RH-1", user_id=head_u.id)
    project = make_project(code="RT-1")
    project.head_employee_id = head_e.id
    db.add(project)
    db.commit()

    rep_pm = make_user("rp@x.com", role=UserRole.project_manager)
    author_e = make_employee(employee_code="RA-1")
    author_e.reporting_pm_id = rep_pm.id  # the responsible PM wins over the Head
    db.add(author_e)
    db.commit()

    recipients = _pm_user_ids(db, project.id, author_e)
    assert recipients == [rep_pm.id]      # responsible PM is targeted
    assert head_u.id not in recipients    # Head is NOT targeted


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
