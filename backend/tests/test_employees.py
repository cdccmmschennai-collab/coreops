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
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.post("/api/v1/employees", headers=h, json=_emp_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["full_name"] == "Priya Ramanujan"
    assert body["status"] == "active"

    got = client.get(f"/api/v1/employees/{body['id']}", headers=h)
    assert got.status_code == 200
    assert got.json()["employee_code"] == "EMP-001"


def test_create_duplicate_code_409(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    assert client.post("/api/v1/employees", headers=h, json=_emp_payload()).status_code == 201
    dup = client.post("/api/v1/employees", headers=h, json=_emp_payload(first_name="Other"))
    assert dup.status_code == 409


def test_create_missing_fields_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.post("/api/v1/employees", headers=h, json={"first_name": "X"})
    assert res.status_code == 422


def test_create_invalid_manager_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.post(
        "/api/v1/employees",
        headers=h,
        json=_emp_payload(manager_id=str(uuid.uuid4())),
    )
    assert res.status_code == 422


def test_update_employee(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
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
    h = auth_header("admin@example.com", role=UserRole.admin)
    emp = make_employee(employee_code="EMP-200")
    res = client.patch(
        f"/api/v1/employees/{emp.id}", headers=h, json={"manager_id": str(emp.id)}
    )
    assert res.status_code == 422


def test_deactivate_removes_from_list(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    emp = make_employee(employee_code="EMP-300")
    assert client.delete(f"/api/v1/employees/{emp.id}", headers=h).status_code == 204
    listed = client.get("/api/v1/employees", headers=h).json()
    assert all(item["id"] != str(emp.id) for item in listed["items"])
    assert client.get(f"/api/v1/employees/{emp.id}", headers=h).status_code == 404


def test_get_unknown_404(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.get(f"/api/v1/employees/{uuid.uuid4()}", headers=h)
    assert res.status_code == 404


# ---------- pagination / search / filter ----------
def test_list_pagination(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    for i in range(3):
        make_employee(employee_code=f"E-{i}", first_name=f"Name{i}")
    page = client.get("/api/v1/employees?limit=2&offset=0", headers=h).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2
    assert page["limit"] == 2


def test_search_by_name(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    make_employee(employee_code="E-a", first_name="Alice", last_name="Wong")
    make_employee(employee_code="E-b", first_name="Bob", last_name="Singh")
    res = client.get("/api/v1/employees?q=alice", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["first_name"] == "Alice"


def test_filter_by_status(client, auth_header, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    make_employee(employee_code="E-act", status=EmployeeStatus.active)
    make_employee(employee_code="E-exit", status=EmployeeStatus.exited)
    res = client.get("/api/v1/employees?status=exited", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["status"] == "exited"


# ---------- RBAC ----------
def test_viewer_can_read_cannot_create(client, auth_header, make_employee):
    make_employee(employee_code="E-v")
    h = auth_header("viewer@example.com", role=UserRole.viewer)
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


def test_manager_sees_team_only(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.manager)
    mgr = make_employee(employee_code="MGR", user_id=mgr_user.id, first_name="Mgr")
    report = make_employee(employee_code="R1", first_name="Report", manager_id=mgr.id)
    make_employee(employee_code="X1", first_name="Outsider")
    h = login("mgr@example.com")
    res = client.get("/api/v1/employees", headers=h).json()
    codes = {item["employee_code"] for item in res["items"]}
    assert codes == {"R1"}
    assert client.get(f"/api/v1/employees/{report.id}", headers=h).status_code == 200


def test_manager_get_nonteam_403(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.manager)
    make_employee(employee_code="MGR", user_id=mgr_user.id)
    outsider = make_employee(employee_code="X1")
    h = login("mgr@example.com")
    assert client.get(f"/api/v1/employees/{outsider.id}", headers=h).status_code == 403


def test_manager_cannot_create_403(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.manager)
    make_employee(employee_code="MGR", user_id=mgr_user.id)
    h = login("mgr@example.com")
    assert client.post("/api/v1/employees", headers=h, json=_emp_payload()).status_code == 403


def test_team_endpoint_returns_reports(client, make_user, make_employee, login):
    mgr_user = make_user("mgr@example.com", role=UserRole.manager)
    mgr = make_employee(employee_code="MGR", user_id=mgr_user.id)
    make_employee(employee_code="R1", manager_id=mgr.id)
    make_employee(employee_code="R2", manager_id=mgr.id)
    h = login("mgr@example.com")
    res = client.get(f"/api/v1/employees/{mgr.id}/team", headers=h)
    assert res.status_code == 200
    assert {e["employee_code"] for e in res.json()} == {"R1", "R2"}
