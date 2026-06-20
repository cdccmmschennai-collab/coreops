"""API tests for the tasks module: CRUD, status updates, RBAC, notifications."""
from app.modules.projects.models import ProjectMemberRole
from app.modules.users.models import UserRole


def _task_payload(assignee_id, **over):
    base = {
        "title": "Prepare Monthly Report",
        "description": "Update SAP extract and verify totals.",
        "assigned_to_employee_id": str(assignee_id),
        "priority": "high",
        "due_date": "2026-06-15",
    }
    base.update(over)
    return base


def _pm_setup(make_user, make_employee, login):
    pm_user = make_user("pm@example.com", role=UserRole.project_manager)
    pm_emp = make_employee(
        employee_code="PM-1", first_name="Pat", last_name="Manager", user_id=pm_user.id
    )
    return login("pm@example.com"), pm_emp


def test_pm_creates_task_and_notifies_assignee(
    client, make_user, make_employee, login
):
    pm_header, pm_emp = _pm_setup(make_user, make_employee, login)
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    assignee = make_employee(
        employee_code="E-1", first_name="Santhosh", last_name="Kumar", user_id=emp_user.id
    )

    res = client.post(
        "/api/v1/tasks",
        headers=pm_header,
        json=_task_payload(assignee.id),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["title"] == "Prepare Monthly Report"
    assert body["status"] == "open"
    assert body["assigned_to_employee_id"] == str(assignee.id)
    assert body["assigned_by_employee_id"] == str(pm_emp.id)
    assert body["assigned_to_name"] == "Santhosh Kumar"
    assert body["assigned_by_name"] == "Pat Manager"

    # Names are also resolved on list + detail reads.
    detail = client.get(f"/api/v1/tasks/{body['id']}", headers=pm_header).json()
    assert detail["assigned_by_name"] == "Pat Manager"
    listing = client.get("/api/v1/tasks", headers=pm_header).json()
    assert listing["items"][0]["assigned_by_name"] == "Pat Manager"

    emp_header = login("emp@example.com")
    notifs = client.get("/api/v1/notifications", headers=emp_header)
    assert notifs.status_code == 200
    assert notifs.json()["total"] == 1
    assert notifs.json()["items"][0]["type"] == "task_assigned"
    assert "Prepare Monthly Report" in notifs.json()["items"][0]["message"]


def test_employee_lists_only_own_tasks(client, make_user, make_employee, login):
    pm_header, _ = _pm_setup(make_user, make_employee, login)
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    other_user = make_user("other@example.com", role=UserRole.employee)
    assignee = make_employee(employee_code="E-1", user_id=emp_user.id)
    other = make_employee(employee_code="E-2", user_id=other_user.id)

    for emp_id, title in [(assignee.id, "Mine"), (other.id, "Theirs")]:
        assert (
            client.post(
                "/api/v1/tasks",
                headers=pm_header,
                json=_task_payload(emp_id, title=title),
            ).status_code
            == 201
        )

    emp_header = login("emp@example.com")
    res = client.get("/api/v1/tasks", headers=emp_header)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Mine"


def test_team_lead_mine_vs_assigned_tabs_are_distinct(
    client, make_user, make_employee, make_project, make_project_member, login
):
    """A team lead is both a receiver (PM can assign them work) and an
    assigner (they hand out work in their led project). `mine=true` must
    show only what's assigned to them; `mine=false` must show only what
    they handed out — the two must not bleed into each other."""
    pm_header, _pm_emp = _pm_setup(make_user, make_employee, login)
    header, lead, member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )

    # PM assigns a task to the lead.
    res = client.post(
        "/api/v1/tasks", headers=pm_header, json=_task_payload(lead.id, title="From PM")
    )
    assert res.status_code == 201, res.text

    # Lead assigns a task to their project member.
    res = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(member.id, project_id=str(project.id), title="To member"),
    )
    assert res.status_code == 201, res.text

    mine = client.get("/api/v1/tasks?mine=true", headers=header).json()
    assert mine["total"] == 1
    assert mine["items"][0]["title"] == "From PM"

    assigned = client.get("/api/v1/tasks?mine=false", headers=header).json()
    assert assigned["total"] == 1
    assert assigned["items"][0]["title"] == "To member"

    # Omitting `mine` keeps the old combined view (back-compat for callers
    # that don't know about the split).
    combined = client.get("/api/v1/tasks", headers=header).json()
    assert combined["total"] == 2


def test_pm_lists_all_tasks(client, make_user, make_employee, login):
    pm_header, _ = _pm_setup(make_user, make_employee, login)
    emp1 = make_employee(employee_code="E-1", user_id=make_user("e1@example.com", role=UserRole.employee).id)
    emp2 = make_employee(employee_code="E-2", user_id=make_user("e2@example.com", role=UserRole.employee).id)

    client.post("/api/v1/tasks", headers=pm_header, json=_task_payload(emp1.id, title="A"))
    client.post("/api/v1/tasks", headers=pm_header, json=_task_payload(emp2.id, title="B"))

    res = client.get("/api/v1/tasks", headers=pm_header)
    assert res.status_code == 200
    assert res.json()["total"] == 2


def test_employee_updates_status(client, make_user, make_employee, login):
    pm_header, _ = _pm_setup(make_user, make_employee, login)
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    assignee = make_employee(employee_code="E-1", user_id=emp_user.id)

    created = client.post(
        "/api/v1/tasks",
        headers=pm_header,
        json=_task_payload(assignee.id),
    ).json()
    emp_header = login("emp@example.com")

    res = client.patch(
        f"/api/v1/tasks/{created['id']}/status",
        headers=emp_header,
        json={"status": "in_progress"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "in_progress"

    res = client.patch(
        f"/api/v1/tasks/{created['id']}/status",
        headers=emp_header,
        json={"status": "completed"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "completed"


def test_employee_cannot_cancel_task(client, make_user, make_employee, login):
    pm_header, _ = _pm_setup(make_user, make_employee, login)
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    assignee = make_employee(employee_code="E-1", user_id=emp_user.id)

    created = client.post(
        "/api/v1/tasks",
        headers=pm_header,
        json=_task_payload(assignee.id),
    ).json()
    emp_header = login("emp@example.com")

    res = client.patch(
        f"/api/v1/tasks/{created['id']}/status",
        headers=emp_header,
        json={"status": "cancelled"},
    )
    assert res.status_code == 422


def test_pm_cancels_task(client, make_user, make_employee, login):
    pm_header, _ = _pm_setup(make_user, make_employee, login)
    assignee = make_employee(employee_code="E-1", user_id=make_user("e@example.com", role=UserRole.employee).id)

    created = client.post(
        "/api/v1/tasks",
        headers=pm_header,
        json=_task_payload(assignee.id),
    ).json()

    res = client.patch(
        f"/api/v1/tasks/{created['id']}",
        headers=pm_header,
        json={"status": "cancelled"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_employee_cannot_create_task(client, auth_header, make_employee):
    emp_header = auth_header("emp@example.com", role=UserRole.employee)
    assignee = make_employee(employee_code="E-1")
    res = client.post(
        "/api/v1/tasks",
        headers=emp_header,
        json=_task_payload(assignee.id),
    )
    assert res.status_code == 403


def test_cannot_assign_to_non_employee(client, make_user, make_employee, login):
    pm_header, pm_emp = _pm_setup(make_user, make_employee, login)

    res = client.post(
        "/api/v1/tasks",
        headers=pm_header,
        json=_task_payload(pm_emp.id),
    )
    assert res.status_code == 422


# ---- Team lead assignment (scoped to a led project) ---------------------------


def _project_with_lead(
    make_user, make_employee, make_project, make_project_member, login
):
    lead_user = make_user("lead@example.com", role=UserRole.employee)
    lead = make_employee(
        employee_code="TL-1", first_name="Alex", last_name="Lead", user_id=lead_user.id
    )
    member_user = make_user("member@example.com", role=UserRole.employee)
    member = make_employee(
        employee_code="C-1", first_name="Nainar", last_name="B", user_id=member_user.id
    )
    project = make_project(code="P-100", name="Alpha")
    make_project_member(
        project_id=project.id, employee_id=lead.id, role=ProjectMemberRole.team_lead
    )
    make_project_member(
        project_id=project.id,
        employee_id=member.id,
        role=ProjectMemberRole.contributor,
    )
    return login("lead@example.com"), lead, member, project


def test_team_lead_assigns_task_to_project_member(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, lead, member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    res = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(member.id, project_id=str(project.id)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["assigned_by_name"] == "Alex Lead"
    assert body["assigned_to_name"] == "Nainar B"
    assert body["project_id"] == str(project.id)
    assert body["project_name"] == "Alpha"


def test_team_lead_requires_a_project(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, _lead, member, _project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    res = client.post(
        "/api/v1/tasks", headers=header, json=_task_payload(member.id)
    )
    assert res.status_code == 422


def test_team_lead_cannot_assign_non_member(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, _lead, _member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    outsider = make_employee(
        employee_code="O-1",
        user_id=make_user("out@example.com", role=UserRole.employee).id,
    )
    res = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(outsider.id, project_id=str(project.id)),
    )
    assert res.status_code == 422


def test_team_lead_cannot_assign_in_unled_project(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, _lead, member, _project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    other = make_project(code="P-200", name="Beta")
    make_project_member(
        project_id=other.id,
        employee_id=member.id,
        role=ProjectMemberRole.contributor,
    )
    res = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(member.id, project_id=str(other.id)),
    )
    assert res.status_code == 403


def test_contributor_cannot_create_task(
    client, make_user, make_employee, make_project, make_project_member, login
):
    _header, lead, _member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    member_header = login("member@example.com")
    res = client.post(
        "/api/v1/tasks",
        headers=member_header,
        json=_task_payload(lead.id, project_id=str(project.id)),
    )
    assert res.status_code == 403


def test_assignable_projects_endpoint(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, _lead, _member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    res = client.get("/api/v1/tasks/assignable-projects", headers=header)
    assert res.status_code == 200, res.text
    data = res.json()
    assert len(data) == 1
    assert data[0]["project_id"] == str(project.id)
    names = [m["name"] for m in data[0]["members"]]
    assert "Nainar B" in names
    assert "Alex Lead" not in names  # excludes the lead themselves

    # A plain contributor leads nothing.
    member_header = login("member@example.com")
    res = client.get("/api/v1/tasks/assignable-projects", headers=member_header)
    assert res.status_code == 200
    assert res.json() == []


def test_team_lead_can_cancel_but_not_edit_assigned_task(
    client, make_user, make_employee, make_project, make_project_member, login
):
    header, _lead, member, project = _project_with_lead(
        make_user, make_employee, make_project, make_project_member, login
    )
    created = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(member.id, project_id=str(project.id)),
    ).json()

    cancel = client.patch(
        f"/api/v1/tasks/{created['id']}", headers=header, json={"status": "cancelled"}
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"

    other = client.post(
        "/api/v1/tasks",
        headers=header,
        json=_task_payload(member.id, project_id=str(project.id), title="Second"),
    ).json()
    edit = client.patch(
        f"/api/v1/tasks/{other['id']}", headers=header, json={"title": "Renamed"}
    )
    assert edit.status_code == 403
