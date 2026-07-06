"""GET /projects/led — projects the caller leads, each with its members.

Re-sources the team-lead detection the Work Reports view previously took from
the (retiring) /tasks/assignable-projects endpoint. Unlike that endpoint, the
led-projects list is a reports-scope filter: it includes ALL active members of
the led project (the lead themselves included).
"""
from app.modules.projects.models import ProjectMemberRole
from app.modules.users.models import UserRole


def test_led_projects_returns_led_project_with_members(
    client, make_user, make_employee, make_project, make_project_member, login
):
    lead_user = make_user("lead@example.com", role=UserRole.employee)
    lead_emp = make_employee(
        employee_code="TL-1", first_name="Alex", last_name="Lead", user_id=lead_user.id
    )
    member_user = make_user("member@example.com", role=UserRole.employee)
    member_emp = make_employee(
        employee_code="C-1", first_name="Nainar", last_name="B", user_id=member_user.id
    )
    project = make_project(code="LED-1", name="Alpha")
    make_project_member(
        project_id=project.id, employee_id=lead_emp.id, role=ProjectMemberRole.team_lead
    )
    make_project_member(
        project_id=project.id,
        employee_id=member_emp.id,
        role=ProjectMemberRole.contributor,
    )

    resp = client.get("/api/v1/projects/led", headers=login("lead@example.com"))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["project_id"] == str(project.id)
    ids = {m["employee_id"] for m in body[0]["members"]}
    assert str(lead_emp.id) in ids and str(member_emp.id) in ids


def test_led_projects_empty_for_non_lead(client, make_user, make_employee, login):
    user = make_user("c@example.com", role=UserRole.employee)
    make_employee(employee_code="C-9", user_id=user.id)
    resp = client.get("/api/v1/projects/led", headers=login("c@example.com"))
    assert resp.status_code == 200
    assert resp.json() == []
