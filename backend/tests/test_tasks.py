"""API tests for the tasks module: CRUD, status updates, RBAC, notifications."""
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
