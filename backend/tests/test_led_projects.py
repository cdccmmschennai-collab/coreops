"""GET /projects/led — projects the caller Heads, each with its members.

Feeds the Work Reports employee-filter visibility signal. Migrated from
team_lead to Head: team leads no longer surface here, mirroring the backend
report scope which is now Head-only. The list includes ALL active members of
the headed project (the Head themselves included).
"""
from app.modules.projects.models import ProjectMemberRole
from app.modules.users.models import UserRole


def test_led_projects_returns_headed_project_with_members(
    db, client, make_user, make_employee, make_project, make_project_member, login
):
    head_user = make_user("head@example.com", role=UserRole.employee)
    head_emp = make_employee(
        employee_code="H-1", first_name="Alex", last_name="Head", user_id=head_user.id
    )
    member_user = make_user("member@example.com", role=UserRole.employee)
    member_emp = make_employee(
        employee_code="C-1", first_name="Nainar", last_name="B", user_id=member_user.id
    )
    project = make_project(code="HEAD-1", name="Alpha")
    project.head_employee_id = head_emp.id
    db.add(project)
    db.commit()
    make_project_member(
        project_id=project.id, employee_id=head_emp.id, role=ProjectMemberRole.contributor
    )
    make_project_member(
        project_id=project.id,
        employee_id=member_emp.id,
        role=ProjectMemberRole.contributor,
    )

    resp = client.get("/api/v1/projects/led", headers=login("head@example.com"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["project_id"] == str(project.id)
    ids = {m["employee_id"] for m in body[0]["members"]}
    assert str(head_emp.id) in ids and str(member_emp.id) in ids


def test_led_projects_empty_for_team_lead_who_is_not_head(
    client, make_user, make_employee, make_project, make_project_member, login
):
    """A team lead (project member, not Head) no longer surfaces here — the
    project-wide report signal now belongs to the Head only."""
    user = make_user("tl@example.com", role=UserRole.employee)
    emp = make_employee(employee_code="TL-9", user_id=user.id)
    project = make_project(code="TL-ONLY", name="Beta")
    make_project_member(
        project_id=project.id, employee_id=emp.id, role=ProjectMemberRole.team_lead
    )
    resp = client.get("/api/v1/projects/led", headers=login("tl@example.com"))
    assert resp.status_code == 200
    assert resp.json() == []


def test_led_projects_empty_for_non_member(client, make_user, make_employee, login):
    user = make_user("c@example.com", role=UserRole.employee)
    make_employee(employee_code="C-9", user_id=user.id)
    resp = client.get("/api/v1/projects/led", headers=login("c@example.com"))
    assert resp.status_code == 200
    assert resp.json() == []
