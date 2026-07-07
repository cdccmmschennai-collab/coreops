"""Phase 3 Task 2 — per-activity staffing APIs.

Covers the service layer: grouped read (lead / contributors / QC), the one-Lead-
per-activity rule, QC as an additive flag, PM-or-Head authorization, the
visibility backbone auto-row, and that only activities with staffing are listed.
"""
import pytest

from app.modules.activity_master import service as am_svc
from app.modules.activity_master.schemas import ActivityCreate
from app.modules.notifications.models import Notification
from app.modules.projects import service as proj_svc
from app.modules.projects.models import ProjectMember, ProjectStatus
from app.modules.projects.schemas import (
    ActivityMemberCreate,
    ActivityMemberUpdate,
)
from app.modules.users.models import UserRole
from app.shared.errors import AppError


def _activity(db, code):
    return am_svc.create_activity(db, ActivityCreate(code=code, name=code))


def _head(db, make_user, make_employee, make_project, pm, code="AS-1"):
    project = make_project(code=code, status=ProjectStatus.active)
    head_u = make_user(f"head-{code}@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code=f"H-{code}", user_id=head_u.id)
    proj_svc.set_project_head(db, pm, project.id, head_e.id)
    return project, head_u, head_e


def test_head_assigns_and_staffing_is_grouped(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    fmtl = _activity(db, "FMTL")

    lead_e = make_employee(employee_code="LD-1")
    con_e = make_employee(employee_code="CN-1")

    proj_svc.assign_activity_member(
        db, head_u, project.id, fmtl.id,
        ActivityMemberCreate(employee_id=lead_e.id, role="lead"),
    )
    proj_svc.assign_activity_member(
        db, head_u, project.id, fmtl.id,
        ActivityMemberCreate(employee_id=con_e.id, role="contributor", is_qc=True),
    )

    groups = proj_svc.list_activity_staffing(db, pm, project.id)
    assert len(groups) == 1
    g = groups[0]
    assert g.activity_code == "FMTL"
    assert g.lead is not None and g.lead.employee_id == lead_e.id
    assert [c.employee_id for c in g.contributors] == [con_e.id]
    # QC is additive: the contributor with is_qc appears in the qc list too.
    assert [q.employee_id for q in g.qc] == [con_e.id]
    assert g.member_count == 2


def test_second_lead_rejected(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "MTL")
    a = make_employee(employee_code="A-1")
    b = make_employee(employee_code="B-1")

    proj_svc.assign_activity_member(
        db, head_u, project.id, act.id, ActivityMemberCreate(employee_id=a.id, role="lead")
    )
    with pytest.raises(AppError) as ei:
        proj_svc.assign_activity_member(
            db, head_u, project.id, act.id, ActivityMemberCreate(employee_id=b.id, role="lead")
        )
    assert ei.value.status_code == 409


def test_visibility_backbone_row_created(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "DOC")
    emp = make_employee(employee_code="V-1")

    proj_svc.assign_activity_member(
        db, head_u, project.id, act.id, ActivityMemberCreate(employee_id=emp.id, role="contributor")
    )
    row = db.query(ProjectMember).filter_by(project_id=project.id, employee_id=emp.id).one_or_none()
    assert row is not None


def test_non_head_employee_cannot_assign(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, _, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "PM")

    outsider_u = make_user("out@x.com", role=UserRole.employee)
    make_employee(employee_code="O-1", user_id=outsider_u.id)
    emp = make_employee(employee_code="T-1")

    with pytest.raises(AppError) as ei:
        proj_svc.assign_activity_member(
            db, outsider_u, project.id, act.id,
            ActivityMemberCreate(employee_id=emp.id, role="contributor"),
        )
    assert ei.value.status_code == 403


def test_update_toggles_qc_and_remove(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "BOM")
    emp = make_employee(employee_code="U-1")

    proj_svc.assign_activity_member(
        db, head_u, project.id, act.id, ActivityMemberCreate(employee_id=emp.id, role="contributor")
    )
    out = proj_svc.update_activity_member(
        db, head_u, project.id, act.id, emp.id, ActivityMemberUpdate(is_qc=True)
    )
    assert out.is_qc is True

    proj_svc.remove_activity_member(db, head_u, project.id, act.id, emp.id)
    assert proj_svc.list_activity_staffing(db, pm, project.id) == []


def test_only_activities_with_staffing_returned(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    used = _activity(db, "USED")
    _activity(db, "UNUSED")  # no assignments — must not appear
    emp = make_employee(employee_code="S-1")

    proj_svc.assign_activity_member(
        db, head_u, project.id, used.id, ActivityMemberCreate(employee_id=emp.id, role="lead")
    )
    groups = proj_svc.list_activity_staffing(db, pm, project.id)
    assert [g.activity_code for g in groups] == ["USED"]


# ---------- Lead self-service (Part 2) -------------------------------------
def _lead_of_activity(db, make_user, make_employee, proj_svc_, project, activity, head_u):
    """Make an employee (with a login) the Lead of one activity; return (user, emp)."""
    lead_u = make_user(f"lead-{activity.code}@x.com", role=UserRole.employee)
    lead_e = make_employee(employee_code=f"LEAD-{activity.code}", user_id=lead_u.id)
    proj_svc_.assign_activity_member(
        db, head_u, project.id, activity.id,
        ActivityMemberCreate(employee_id=lead_e.id, role="lead"),
    )
    return lead_u, lead_e


def test_lead_can_add_and_remove_contributor_on_own_activity(
    db, make_user, make_employee, make_project
):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "FMTL")
    lead_u, _ = _lead_of_activity(db, make_user, make_employee, proj_svc, project, act, head_u)
    con = make_employee(employee_code="C-1")

    # Add a Contributor (with QC) to their own activity.
    proj_svc.assign_activity_member(
        db, lead_u, project.id, act.id,
        ActivityMemberCreate(employee_id=con.id, role="contributor", is_qc=True),
    )
    # Remove it again.
    proj_svc.remove_activity_member(db, lead_u, project.id, act.id, con.id)
    g = proj_svc.list_activity_staffing(db, pm, project.id)[0]
    assert g.contributors == []


def test_lead_cannot_add_second_lead(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "MTL")
    lead_u, _ = _lead_of_activity(db, make_user, make_employee, proj_svc, project, act, head_u)
    other = make_employee(employee_code="O-1")

    with pytest.raises(AppError) as ei:
        proj_svc.assign_activity_member(
            db, lead_u, project.id, act.id,
            ActivityMemberCreate(employee_id=other.id, role="lead"),
        )
    assert ei.value.status_code == 403


def test_lead_cannot_remove_the_lead(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "DOC")
    lead_u, lead_e = _lead_of_activity(db, make_user, make_employee, proj_svc, project, act, head_u)

    with pytest.raises(AppError) as ei:
        proj_svc.remove_activity_member(db, lead_u, project.id, act.id, lead_e.id)
    assert ei.value.status_code == 403


def test_lead_cannot_manage_other_activity(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    mine = _activity(db, "MINE")
    other = _activity(db, "OTHER")
    lead_u, _ = _lead_of_activity(db, make_user, make_employee, proj_svc, project, mine, head_u)
    emp = make_employee(employee_code="X-1")

    with pytest.raises(AppError) as ei:
        proj_svc.assign_activity_member(
            db, lead_u, project.id, other.id,
            ActivityMemberCreate(employee_id=emp.id, role="contributor"),
        )
    assert ei.value.status_code == 403


def test_lead_cannot_promote_contributor_to_lead(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "BOM")
    lead_u, _ = _lead_of_activity(db, make_user, make_employee, proj_svc, project, act, head_u)
    con = make_employee(employee_code="C-2")
    proj_svc.assign_activity_member(
        db, lead_u, project.id, act.id,
        ActivityMemberCreate(employee_id=con.id, role="contributor"),
    )

    # Changing the Lead assignment is barred; only QC toggling is allowed.
    with pytest.raises(AppError) as ei:
        proj_svc.update_activity_member(
            db, lead_u, project.id, act.id, con.id,
            ActivityMemberUpdate(role="lead"),
        )
    assert ei.value.status_code == 403
    # QC toggling on a contributor is fine.
    out = proj_svc.update_activity_member(
        db, lead_u, project.id, act.id, con.id, ActivityMemberUpdate(is_qc=True)
    )
    assert out.is_qc is True


def test_contributor_cannot_manage_staffing(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "PM")
    con_u = make_user("con@x.com", role=UserRole.employee)
    con_e = make_employee(employee_code="CON-1", user_id=con_u.id)
    proj_svc.assign_activity_member(
        db, head_u, project.id, act.id,
        ActivityMemberCreate(employee_id=con_e.id, role="contributor"),
    )
    target = make_employee(employee_code="T-2")

    with pytest.raises(AppError) as ei:
        proj_svc.assign_activity_member(
            db, con_u, project.id, act.id,
            ActivityMemberCreate(employee_id=target.id, role="contributor"),
        )
    assert ei.value.status_code == 403


# ---------- assignment notifications (Part 1) ------------------------------
def _notifs_for(db, user_id):
    return db.query(Notification).filter_by(user_id=user_id, type="project_assigned").all()


def test_head_assignment_notifies_head(db, make_user, make_employee, make_project):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="NP-1", name="Nova", status=ProjectStatus.active)
    head_u = make_user("head@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-1", user_id=head_u.id)

    proj_svc.set_project_head(db, pm, project.id, head_e.id)

    notes = _notifs_for(db, head_u.id)
    assert len(notes) == 1
    n = notes[0]
    assert n.title == "You have been assigned to a project"
    assert "Nova" in n.message and "NP-1" in n.message
    assert "Role:\nHead" in n.message
    assert "Activity:" not in n.message  # Head has no activity
    assert n.target_url == f"/projects/{project.id}"


def test_activity_assignment_notifies_member_with_content(
    db, make_user, make_employee, make_project
):
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="AP-1", name="Atlas", status=ProjectStatus.active)
    head_u = make_user("head@x.com", role=UserRole.employee)
    head_e = make_employee(employee_code="HD-2", user_id=head_u.id,
                           first_name="Hedy", last_name="Boss")
    proj_svc.set_project_head(db, pm, project.id, head_e.id)
    act = _activity(db, "FMTL")

    con_u = make_user("con@x.com", role=UserRole.employee)
    con_e = make_employee(employee_code="CN-9", user_id=con_u.id)
    proj_svc.assign_activity_member(
        db, head_u, project.id, act.id,
        ActivityMemberCreate(employee_id=con_e.id, role="contributor", is_qc=True),
    )

    notes = _notifs_for(db, con_u.id)
    assert len(notes) == 1
    msg = notes[0].message
    assert "Project:\nAtlas" in msg
    assert "Code:\nAP-1" in msg
    assert "Role:\nQC" in msg          # is_qc → QC label
    assert "Activity:\nFMTL" in msg
    assert "Assigned by:\nHedy Boss" in msg


def test_assigner_is_not_notified(db, make_user, make_employee, make_project):
    """A Lead who assigns a Contributor does not notify themselves."""
    pm = make_user("pm@x.com", role=UserRole.project_manager)
    project, head_u, _ = _head(db, make_user, make_employee, make_project, pm)
    act = _activity(db, "MTL")
    lead_u, _ = _lead_of_activity(db, make_user, make_employee, proj_svc, project, act, head_u)
    con_u = make_user("con@x.com", role=UserRole.employee)
    con_e = make_employee(employee_code="CN-8", user_id=con_u.id)

    # The Lead already has one notification (from being assigned Lead by the Head).
    lead_before = len(_notifs_for(db, lead_u.id))
    proj_svc.assign_activity_member(
        db, lead_u, project.id, act.id,
        ActivityMemberCreate(employee_id=con_e.id, role="contributor"),
    )
    assert len(_notifs_for(db, con_u.id)) == 1        # the contributor is notified
    assert len(_notifs_for(db, lead_u.id)) == lead_before  # the assigner is not
