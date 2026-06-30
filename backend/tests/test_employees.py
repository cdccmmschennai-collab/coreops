"""API tests for the employees module: CRUD, search/filter/pagination, RBAC."""
import uuid

from app.modules.employees.models import EmployeeStatus
from app.modules.users.models import UserRole


def _emp_payload(**over):
    base = {
        "employee_code": "EMP-001",
        "first_name": "Priya",
        "last_name": "Ramanujan",
        "department": "Platform",
        "designation": "Senior Engineer",
    }
    base.update(over)
    return base


# ---------- admin CRUD ----------
def test_admin_create_and_get(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/employees", headers=h, json=_emp_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["full_name"] == "Priya Ramanujan"
    assert body["status"] == "active"

    got = client.get(f"/api/v1/employees/{body['id']}", headers=h)
    assert got.status_code == 200
    assert got.json()["employee_code"] == "EMP-001"


def test_create_duplicate_code_409(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    assert client.post("/api/v1/employees", headers=h, json=_emp_payload()).status_code == 201
    dup = client.post("/api/v1/employees", headers=h, json=_emp_payload(first_name="Other"))
    assert dup.status_code == 409


def test_create_missing_fields_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/employees", headers=h, json={"first_name": "X"})
    assert res.status_code == 422


def test_create_invalid_manager_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/employees",
        headers=h,
        json=_emp_payload(manager_id=str(uuid.uuid4())),
    )
    assert res.status_code == 422


def test_update_employee(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EMP-100")
    res = client.patch(
        f"/api/v1/employees/{emp.id}",
        headers=h,
        json={"designation": "Lead", "status": "on_leave"},
    )
    assert res.status_code == 200
    assert res.json()["designation"] == "Lead"
    assert res.json()["status"] == "on_leave"


def test_update_self_manager_422(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EMP-200")
    res = client.patch(
        f"/api/v1/employees/{emp.id}", headers=h, json={"manager_id": str(emp.id)}
    )
    assert res.status_code == 422


def test_deactivate_removes_from_list(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EMP-300")
    assert client.delete(f"/api/v1/employees/{emp.id}", headers=h).status_code == 204
    listed = client.get("/api/v1/employees", headers=h).json()
    assert all(item["id"] != str(emp.id) for item in listed["items"])
    assert client.get(f"/api/v1/employees/{emp.id}", headers=h).status_code == 404


def test_get_unknown_404(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.get(f"/api/v1/employees/{uuid.uuid4()}", headers=h)
    assert res.status_code == 404


# ---------- pagination / search / filter ----------
def test_list_pagination(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    for i in range(3):
        make_employee(employee_code=f"E-{i}", first_name=f"Name{i}")
    page = client.get("/api/v1/employees?limit=2&offset=0", headers=h).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2


def test_search_by_name(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    make_employee(employee_code="E-a", first_name="Alice", last_name="Wong")
    make_employee(employee_code="E-b", first_name="Bob", last_name="Singh")
    res = client.get("/api/v1/employees?q=alice", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["first_name"] == "Alice"


def test_filter_by_status(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    make_employee(employee_code="E-act", status=EmployeeStatus.active)
    make_employee(employee_code="E-exit", status=EmployeeStatus.exited)
    res = client.get("/api/v1/employees?status=exited", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["status"] == "exited"


# ---------- RBAC ----------
def test_viewer_can_read_cannot_create(client, auth_header, make_employee):
    make_employee(employee_code="E-v")
    h = auth_header("viewer@example.com", role=UserRole.employee)
    assert client.get("/api/v1/employees", headers=h).status_code == 200
    assert client.post("/api/v1/employees", headers=h, json=_emp_payload()).status_code == 403


def test_employee_sees_only_self(client, make_user, make_employee, login):
    me_user = make_user("emp@example.com", role=UserRole.employee)
    make_employee(employee_code="SELF", user_id=me_user.id, first_name="Self")
    make_employee(employee_code="OTHER", first_name="Other")
    h = login("emp@example.com")
    res = client.get("/api/v1/employees", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["employee_code"] == "SELF"


def test_employee_cannot_view_other_403(client, make_user, make_employee, login):
    me_user = make_user("emp@example.com", role=UserRole.employee)
    make_employee(employee_code="SELF", user_id=me_user.id)
    other = make_employee(employee_code="OTHER")
    h = login("emp@example.com")
    assert client.get(f"/api/v1/employees/{other.id}", headers=h).status_code == 403


def test_project_manager_sees_all_employees(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mgr_user.id, first_name="Mgr")
    report = make_employee(employee_code="R1", first_name="Report", manager_id=mgr.id)
    make_employee(employee_code="X1", first_name="Outsider")
    h = login("mgr@example.com")
    res = client.get("/api/v1/employees", headers=h).json()
    codes = {item["employee_code"] for item in res["items"]}
    # project_manager sees ALL employees
    assert "MGR" in codes and "R1" in codes and "X1" in codes
    assert client.get(f"/api/v1/employees/{report.id}", headers=h).status_code == 200


def test_project_manager_can_view_any_employee(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR", user_id=mgr_user.id)
    outsider = make_employee(employee_code="X1")
    h = login("mgr@example.com")
    # project_manager has full read access
    assert client.get(f"/api/v1/employees/{outsider.id}", headers=h).status_code == 200


def test_project_manager_can_create_employee(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR", user_id=mgr_user.id)
    h = login("mgr@example.com")
    # project_manager has full employee management access
    assert client.post("/api/v1/employees", headers=h, json=_emp_payload()).status_code == 201


def test_team_endpoint_returns_reports(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mgr_user.id)
    make_employee(employee_code="R1", manager_id=mgr.id)
    make_employee(employee_code="R2", manager_id=mgr.id)
    h = login("mgr@example.com")
    res = client.get(f"/api/v1/employees/{mgr.id}/team", headers=h)
    assert res.status_code == 200
    assert {e["employee_code"] for e in res.json()} == {"R1", "R2"}


# ---------- account management ----------

def test_create_account_links_user(client, make_user, make_employee, login):
    """PM can create a login account and link it to an employee."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="ACC-001")
    h = login("pm@example.com")
    res = client.post(
        f"/api/v1/employees/{emp.id}/account",
        headers=h,
        json={"email": "newhire@company.com", "password": "Secure1234", "role": "employee"},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["email"] == "newhire@company.com"
    assert body["role"] == "employee"
    assert body["is_active"] is True

    # The employee record should now carry the user_id.
    emp_data = client.get(f"/api/v1/employees/{emp.id}", headers=h).json()
    assert emp_data["user_id"] == body["id"]


def test_create_account_duplicate_409(client, make_user, make_employee, login):
    """Creating a second account for the same employee is rejected."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    existing_user = make_user("already@company.com")
    emp = make_employee(employee_code="ACC-002", user_id=existing_user.id)
    h = login("pm@example.com")
    res = client.post(
        f"/api/v1/employees/{emp.id}/account",
        headers=h,
        json={"email": "second@company.com", "password": "Secure1234", "role": "employee"},
    )
    assert res.status_code == 409


def test_create_account_duplicate_email_409(client, make_user, make_employee, login):
    """Email already in use by another user returns 409."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    make_user("taken@company.com")
    emp = make_employee(employee_code="ACC-003")
    h = login("pm@example.com")
    res = client.post(
        f"/api/v1/employees/{emp.id}/account",
        headers=h,
        json={"email": "taken@company.com", "password": "Secure1234", "role": "employee"},
    )
    assert res.status_code == 409


def test_create_account_employee_forbidden(client, make_user, make_employee, login):
    """Employees cannot create accounts for others."""
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    emp = make_employee(employee_code="ACC-004", user_id=emp_user.id)
    other = make_employee(employee_code="OTHER-004")
    h = login("emp@example.com")
    res = client.post(
        f"/api/v1/employees/{other.id}/account",
        headers=h,
        json={"email": "other@company.com", "password": "Secure1234", "role": "employee"},
    )
    assert res.status_code == 403


def test_reset_account_password(client, make_user, make_employee, login):
    """PM can reset the linked account's password."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp_user = make_user("hire@company.com")
    emp = make_employee(employee_code="ACC-005", user_id=emp_user.id)
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/password",
        headers=h,
        json={"new_password": "NewPass9999"},
    )
    assert res.status_code == 204

    # New password should work at login.
    login_res = client.post(
        "/api/v1/auth/login", json={"identifier": "hire@company.com", "password": "NewPass9999"}
    )
    assert login_res.status_code == 200


def test_disable_and_enable_account(client, make_user, make_employee, login):
    """PM can disable then re-enable a linked account."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp_user = make_user("active@company.com")
    emp = make_employee(employee_code="ACC-006", user_id=emp_user.id)
    h = login("pm@example.com")

    # Disable.
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/status",
        headers=h,
        json={"is_active": False},
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Disabled user cannot log in.
    login_res = client.post(
        "/api/v1/auth/login", json={"identifier": "active@company.com", "password": "password123"}
    )
    assert login_res.status_code == 401

    # Re-enable.
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/status",
        headers=h,
        json={"is_active": True},
    )
    assert res.status_code == 200
    assert res.json()["is_active"] is True


def test_account_password_no_account_404(client, make_user, make_employee, login):
    """Reset password for employee with no linked account returns 404."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="ACC-007")
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/password",
        headers=h,
        json={"new_password": "NewPass9999"},
    )
    assert res.status_code == 404


# ---------- account role change ----------

def test_change_account_role(client, make_user, make_employee, login):
    """PM can change the linked account's role from Employee Details."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp_user = make_user("worker@company.com", role=UserRole.employee)
    emp = make_employee(employee_code="ROLE-1", user_id=emp_user.id)
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/role",
        headers=h,
        json={"role": "project_manager"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["role"] == "project_manager"


def test_change_account_role_no_account_404(client, make_user, make_employee, login):
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="ROLE-2")
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/role",
        headers=h,
        json={"role": "project_manager"},
    )
    assert res.status_code == 404


def test_change_account_role_employee_forbidden(client, make_user, make_employee, login):
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    emp = make_employee(employee_code="ROLE-3", user_id=emp_user.id)
    h = login("emp@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/role",
        headers=h,
        json={"role": "project_manager"},
    )
    assert res.status_code == 403


# ---------- account relink / unlink ----------

def test_relink_account_to_existing_user(client, make_user, make_employee, login):
    """PM can repoint an employee to a different existing user (one-to-one)."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    old_user = make_user("old@company.com")
    new_user = make_user("new@company.com")
    emp = make_employee(employee_code="LINK-1", user_id=old_user.id)
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/link",
        headers=h,
        json={"user_id": str(new_user.id)},
    )
    assert res.status_code == 200, res.text
    assert res.json()["id"] == str(new_user.id)
    emp_data = client.get(f"/api/v1/employees/{emp.id}", headers=h).json()
    assert emp_data["user_id"] == str(new_user.id)


def test_relink_account_already_linked_409(client, make_user, make_employee, login):
    """Relinking to a user already owned by another employee is rejected."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    taken_user = make_user("taken@company.com")
    make_employee(employee_code="LINK-2A", user_id=taken_user.id)
    emp = make_employee(employee_code="LINK-2B")
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/link",
        headers=h,
        json={"user_id": str(taken_user.id)},
    )
    assert res.status_code == 409


def test_relink_account_unknown_user_422(client, make_user, make_employee, login):
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="LINK-3")
    h = login("pm@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/link",
        headers=h,
        json={"user_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert res.status_code == 422


def test_unlink_account(client, make_user, make_employee, login):
    """Unlink detaches the user but keeps the user row intact."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp_user = make_user("detach@company.com")
    emp = make_employee(employee_code="LINK-4", user_id=emp_user.id)
    h = login("pm@example.com")
    res = client.delete(f"/api/v1/employees/{emp.id}/account/link", headers=h)
    assert res.status_code == 204
    emp_data = client.get(f"/api/v1/employees/{emp.id}", headers=h).json()
    assert emp_data["user_id"] is None
    # User row still exists and can still authenticate.
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": "detach@company.com", "password": "password123"},
    ).status_code == 200


def test_unlink_account_no_account_404(client, make_user, make_employee, login):
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="LINK-5")
    h = login("pm@example.com")
    res = client.delete(f"/api/v1/employees/{emp.id}/account/link", headers=h)
    assert res.status_code == 404


def test_relink_account_employee_forbidden(client, make_user, make_employee, login):
    emp_user = make_user("emp@example.com", role=UserRole.employee)
    emp = make_employee(employee_code="LINK-6", user_id=emp_user.id)
    other_user = make_user("other@company.com")
    h = login("emp@example.com")
    res = client.patch(
        f"/api/v1/employees/{emp.id}/account/link",
        headers=h,
        json={"user_id": str(other_user.id)},
    )
    assert res.status_code == 403


# ---------- manager hierarchy ----------

def test_manager_id_is_exposed_on_employee(client, make_user, make_employee, login):
    """The manager_id FK is returned in EmployeeOut."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR-H1")
    report = make_employee(employee_code="REP-H1", manager_id=mgr.id)
    h = login("pm@example.com")
    data = client.get(f"/api/v1/employees/{report.id}", headers=h).json()
    assert data["manager_id"] == str(mgr.id)


def test_team_empty_for_no_reports(client, make_user, make_employee, login):
    """An employee with no direct reports returns an empty team list."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="LONE-001")
    h = login("pm@example.com")
    res = client.get(f"/api/v1/employees/{emp.id}/team", headers=h)
    assert res.status_code == 200
    assert res.json() == []


def test_team_does_not_include_exited_employees(client, make_user, make_employee, login):
    """Soft-deleted / exited employees do not appear in the team list."""
    pm = make_user("pm@example.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR-EXIT")
    make_employee(employee_code="ACTIVE-R", manager_id=mgr.id, status=EmployeeStatus.active)
    exited = make_employee(employee_code="EXITED-R", manager_id=mgr.id)
    # Soft-delete the exited employee via the API.
    h = login("pm@example.com")
    client.delete(f"/api/v1/employees/{exited.id}", headers=h)

    res = client.get(f"/api/v1/employees/{mgr.id}/team", headers=h)
    assert res.status_code == 200
    codes = {e["employee_code"] for e in res.json()}
    assert "ACTIVE-R" in codes
    assert "EXITED-R" not in codes
