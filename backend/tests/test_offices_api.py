"""API tests for the offices module: CRUD and RBAC."""
from app.modules.users.models import UserRole


def _office_payload(**overrides):
    base = {
        "name": "Test Office",
        "timezone": "Asia/Kolkata",
        "shift_start": "09:00:00",
        "shift_end": "17:30:00",
        "break_minutes": 30,
        "is_active": True,
    }
    base.update(overrides)
    return base


# ---------- RBAC: only admin may call any endpoint ----------

def test_non_admin_list_403(client, auth_header):
    h = auth_header("emp@example.com", role=UserRole.employee)
    assert client.get("/api/v1/offices", headers=h).status_code == 403


def test_project_manager_can_list_offices(client, auth_header):
    h = auth_header("mgr@example.com", role=UserRole.project_manager)
    # project_manager has full access including offices
    assert client.get("/api/v1/offices", headers=h).status_code == 200


def test_non_admin_create_403(client, auth_header):
    h = auth_header("emp@example.com", role=UserRole.employee)
    assert client.post("/api/v1/offices", headers=h, json=_office_payload()).status_code == 403


# ---------- Admin CRUD ----------

def test_admin_create_and_get(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/offices", headers=h, json=_office_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "Test Office"
    assert body["timezone"] == "Asia/Kolkata"
    assert body["shift_start"] == "09:00:00"
    assert body["shift_end"] == "17:30:00"
    assert body["break_minutes"] == 30
    assert body["is_active"] is True

    got = client.get(f"/api/v1/offices/{body['id']}", headers=h)
    assert got.status_code == 200
    assert got.json()["name"] == "Test Office"


def test_admin_list(client, auth_header, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    make_office(name="Office A")
    make_office(name="Office B")
    res = client.get("/api/v1/offices", headers=h).json()
    assert res["total"] == 2
    assert len(res["items"]) == 2
    # sorted by name
    names = [o["name"] for o in res["items"]]
    assert names == sorted(names)


def test_admin_update(client, auth_header, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    office = make_office(name="Before Update")
    res = client.patch(
        f"/api/v1/offices/{office.id}",
        headers=h,
        json={"name": "After Update", "break_minutes": 60},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "After Update"
    assert body["break_minutes"] == 60


def test_get_nonexistent_404(client, auth_header):
    import uuid
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    assert client.get(f"/api/v1/offices/{uuid.uuid4()}", headers=h).status_code == 404


def test_duplicate_name_409(client, auth_header, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    make_office(name="Unique Office")
    res = client.post("/api/v1/offices", headers=h, json=_office_payload(name="Unique Office"))
    assert res.status_code == 409


def test_create_missing_required_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/offices", headers=h, json={"name": "Incomplete"})
    assert res.status_code == 422


def test_break_minutes_out_of_range_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/offices",
        headers=h,
        json=_office_payload(break_minutes=999),
    )
    assert res.status_code == 422


# ---------- Employee office assignment ----------

def test_create_employee_with_office(client, auth_header, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    office = make_office(name="Chennai")
    res = client.post(
        "/api/v1/employees",
        headers=h,
        json={
            "employee_code": "EMP-O1",
            "first_name": "Test",
            "last_name": "Employee",
            "office_id": str(office.id),
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["office_id"] == str(office.id)


def test_update_employee_office(client, auth_header, make_employee, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EMP-O2")
    office = make_office(name="Qatar")

    res = client.patch(
        f"/api/v1/employees/{emp.id}",
        headers=h,
        json={"office_id": str(office.id)},
    )
    assert res.status_code == 200
    assert res.json()["office_id"] == str(office.id)


def test_update_employee_clear_office(client, auth_header, make_employee, make_office):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    office = make_office(name="Hyderabad")
    emp = make_employee(employee_code="EMP-O3")
    # First assign
    client.patch(f"/api/v1/employees/{emp.id}", headers=h, json={"office_id": str(office.id)})
    # Then clear
    res = client.patch(f"/api/v1/employees/{emp.id}", headers=h, json={"office_id": None})
    assert res.status_code == 200
    assert res.json()["office_id"] is None


def test_employee_invalid_office_id_422(client, auth_header):
    import uuid
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/employees",
        headers=h,
        json={
            "employee_code": "EMP-O4",
            "first_name": "Test",
            "last_name": "Employee",
            "office_id": str(uuid.uuid4()),
        },
    )
    assert res.status_code == 422


def test_existing_employee_no_office_valid(client, auth_header, make_employee):
    """Existing employees without office_id remain valid (nullable FK)."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    emp = make_employee(employee_code="EMP-O5")
    res = client.get(f"/api/v1/employees/{emp.id}", headers=h)
    assert res.status_code == 200
    assert res.json()["office_id"] is None
