"""Tests for the job_codes module: CRUD, RBAC, filtering."""
import uuid

from app.modules.users.models import UserRole


# ── helpers ─────────────────────────────────────────────────────────────────

def _create(client, headers, code="J-TEST-1", name="Test Job Code") -> dict:
    res = client.post(
        "/api/v1/job-codes",
        json={"code": code, "name": name},
        headers=headers,
    )
    assert res.status_code == 201, res.text
    return res.json()


# ── creation ─────────────────────────────────────────────────────────────────

def test_admin_can_create(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    data = _create(client, h, code="J-615-2", name="BCEC Project")
    assert data["code"] == "J-615-2"
    assert data["is_active"] is True
    assert data["description"] is None


def test_create_with_description(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    res = client.post(
        "/api/v1/job-codes",
        json={"code": "P389", "name": "Multi-contract Code", "description": "Used across 10 contracts"},
        headers=h,
    )
    assert res.status_code == 201
    assert res.json()["description"] == "Used across 10 contracts"


def test_non_admin_cannot_create(client, auth_header):
    h = auth_header(email="emp@x.com", role=UserRole.employee)
    res = client.post(
        "/api/v1/job-codes",
        json={"code": "J-BLOCKED", "name": "Blocked"},
        headers=h,
    )
    assert res.status_code == 403


def test_duplicate_code_conflict(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="J-DUP-1", name="First")
    res = client.post(
        "/api/v1/job-codes",
        json={"code": "J-DUP-1", "name": "Second"},
        headers=h,
    )
    assert res.status_code == 409


def test_unauthenticated_cannot_create(client):
    res = client.post("/api/v1/job-codes", json={"code": "X", "name": "X"})
    assert res.status_code == 401


# ── listing ──────────────────────────────────────────────────────────────────

def test_list_active_only_by_default(client, auth_header, db):
    from app.modules.job_codes.models import JobCode
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="J-ACTIVE-1", name="Active")
    inactive = JobCode(code="J-INACTIVE-1", name="Inactive", is_active=False)
    db.add(inactive)
    db.commit()

    res = client.get("/api/v1/job-codes", headers=h)
    assert res.status_code == 200
    codes = [r["code"] for r in res.json()["items"]]
    assert "J-ACTIVE-1" in codes
    assert "J-INACTIVE-1" not in codes


def test_list_active_only_false(client, auth_header, db):
    from app.modules.job_codes.models import JobCode
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="J-ACTIVE-2", name="Active")
    inactive = JobCode(code="J-INACTIVE-2", name="Inactive", is_active=False)
    db.add(inactive)
    db.commit()

    res = client.get("/api/v1/job-codes?active_only=false", headers=h)
    codes = [r["code"] for r in res.json()["items"]]
    assert "J-ACTIVE-2" in codes
    assert "J-INACTIVE-2" in codes


def test_employee_can_list(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    _create(client, h_admin, code="J-EMP-LIST", name="Visible")

    h_emp = auth_header(email="emp@x.com", role=UserRole.employee)
    res = client.get("/api/v1/job-codes", headers=h_emp)
    assert res.status_code == 200
    assert res.json()["total"] >= 1


def test_list_unauthenticated(client):
    res = client.get("/api/v1/job-codes")
    assert res.status_code == 401


def test_list_sorted_by_code(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="Z-LAST", name="Last Alphabetically")
    _create(client, h, code="A-FIRST", name="First Alphabetically")

    res = client.get("/api/v1/job-codes", headers=h)
    codes = [r["code"] for r in res.json()["items"]]
    assert codes.index("A-FIRST") < codes.index("Z-LAST")


# ── get one ──────────────────────────────────────────────────────────────────

def test_get_one(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="J-GET-1", name="Get Me")
    res = client.get(f"/api/v1/job-codes/{created['id']}", headers=h)
    assert res.status_code == 200
    assert res.json()["code"] == "J-GET-1"


def test_get_not_found(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    res = client.get(f"/api/v1/job-codes/{uuid.uuid4()}", headers=h)
    assert res.status_code == 404


# ── update ───────────────────────────────────────────────────────────────────

def test_update_name(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="J-UPD-1", name="Old Name")
    res = client.patch(
        f"/api/v1/job-codes/{created['id']}",
        json={"name": "New Name"},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"
    assert res.json()["code"] == "J-UPD-1"  # code is immutable


def test_update_description(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="J-UPD-2", name="With Desc")
    res = client.patch(
        f"/api/v1/job-codes/{created['id']}",
        json={"description": "Added later"},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["description"] == "Added later"


def test_non_admin_cannot_update(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    created = _create(client, h_admin, code="J-GUARD-1", name="Protected")

    h_emp = auth_header(email="emp2@x.com", role=UserRole.employee)
    res = client.patch(
        f"/api/v1/job-codes/{created['id']}",
        json={"name": "Hacked"},
        headers=h_emp,
    )
    assert res.status_code == 403


# ── deactivate ───────────────────────────────────────────────────────────────

def test_deactivate(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="J-DEL-1", name="Deactivate Me")
    res = client.delete(f"/api/v1/job-codes/{created['id']}", headers=h)
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Not in default list
    list_res = client.get("/api/v1/job-codes", headers=h)
    codes = [r["code"] for r in list_res.json()["items"]]
    assert "J-DEL-1" not in codes

    # Appears when active_only=false
    all_res = client.get("/api/v1/job-codes?active_only=false", headers=h)
    codes_all = [r["code"] for r in all_res.json()["items"]]
    assert "J-DEL-1" in codes_all


def test_non_admin_cannot_deactivate(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    created = _create(client, h_admin, code="J-DEL-2", name="Protected Del")

    h_emp = auth_header(email="emp3@x.com", role=UserRole.employee)
    res = client.delete(f"/api/v1/job-codes/{created['id']}", headers=h_emp)
    assert res.status_code == 403


# ── deactivated code can be reused ───────────────────────────────────────────

def test_deactivated_code_allows_new_active(client, auth_header):
    """After deactivating J-REUSE, creating another with the same code must succeed
    because the unique index is partial (WHERE is_active = true)."""
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="J-REUSE", name="Original")
    client.delete(f"/api/v1/job-codes/{created['id']}", headers=h)

    # Creating a new one with the same code should work
    res = client.post(
        "/api/v1/job-codes",
        json={"code": "J-REUSE", "name": "New Active"},
        headers=h,
    )
    assert res.status_code == 201
    assert res.json()["is_active"] is True
