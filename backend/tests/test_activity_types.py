"""Tests for the activity_types module: CRUD, RBAC, filtering."""
from app.modules.activity_types.models import ActivityType
from app.modules.users.models import UserRole


# ── helpers ─────────────────────────────────────────────────────────────────

def _create(client, headers, **kwargs) -> dict:
    payload = {"code": "99", "name": "Test Activity", "category": "GENERAL", "requires_project": False}
    payload.update(kwargs)
    res = client.post("/api/v1/activity-types", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ── creation ─────────────────────────────────────────────────────────────────

def test_admin_can_create(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    data = _create(client, h, code="10", name="Admin Support", category="GENERAL")
    assert data["code"] == "10"
    assert data["is_active"] is True
    assert data["requires_project"] is False


def test_non_admin_cannot_create(client, auth_header):
    h = auth_header(email="emp@x.com", role=UserRole.employee)
    res = client.post(
        "/api/v1/activity-types",
        json={"code": "20", "name": "Foo", "category": "GENERAL"},
        headers=h,
    )
    assert res.status_code == 403


def test_create_project_category_sets_requires_project(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    data = _create(client, h, code="30", name="Project Work", category="PROJECT", requires_project=True)
    assert data["category"] == "PROJECT"
    assert data["requires_project"] is True


def test_create_invalid_category_rejected(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    res = client.post(
        "/api/v1/activity-types",
        json={"code": "40", "name": "Bad", "category": "UNKNOWN"},
        headers=h,
    )
    assert res.status_code == 422


def test_create_without_code(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    res = client.post(
        "/api/v1/activity-types",
        json={"name": "Robot Calibration", "category": "GENERAL"},
        headers=h,
    )
    assert res.status_code == 201, res.text
    assert res.json()["code"] is None
    assert res.json()["name"] == "Robot Calibration"


def test_duplicate_code_conflict(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="50", name="First")
    res = client.post(
        "/api/v1/activity-types",
        json={"code": "50", "name": "Second", "category": "GENERAL"},
        headers=h,
    )
    assert res.status_code == 409


# ── listing ──────────────────────────────────────────────────────────────────

def test_list_returns_active_only_by_default(client, auth_header, db):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="A1", name="Active")
    # Insert inactive directly
    inactive = ActivityType(code="A2", name="Inactive", category="GENERAL", is_active=False)
    db.add(inactive)
    db.commit()

    res = client.get("/api/v1/activity-types", headers=h)
    assert res.status_code == 200
    codes = [r["code"] for r in res.json()["items"]]
    assert "A1" in codes
    assert "A2" not in codes


def test_list_active_only_false_returns_all(client, auth_header, db):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="B1", name="Active")
    inactive = ActivityType(code="B2", name="Inactive", category="GENERAL", is_active=False)
    db.add(inactive)
    db.commit()

    res = client.get("/api/v1/activity-types?active_only=false", headers=h)
    codes = [r["code"] for r in res.json()["items"]]
    assert "B1" in codes
    assert "B2" in codes


def test_list_filter_by_category(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="C1", name="General One", category="GENERAL")
    _create(client, h, code="C2", name="Project One", category="PROJECT", requires_project=True)

    res = client.get("/api/v1/activity-types?category=PROJECT", headers=h)
    assert res.status_code == 200
    codes = [r["code"] for r in res.json()["items"]]
    assert "C1" not in codes
    assert "C2" in codes


def test_list_filter_requires_project(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    _create(client, h, code="D1", name="No project", category="GENERAL", requires_project=False)
    _create(client, h, code="D2", name="Needs project", category="PROJECT", requires_project=True)

    res = client.get("/api/v1/activity-types?requires_project=true", headers=h)
    codes = [r["code"] for r in res.json()["items"]]
    assert "D1" not in codes
    assert "D2" in codes


def test_employee_can_list(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    _create(client, h_admin, code="E1", name="Listed")

    h_emp = auth_header(email="emp@x.com", role=UserRole.employee)
    res = client.get("/api/v1/activity-types", headers=h_emp)
    assert res.status_code == 200


# ── get one ──────────────────────────────────────────────────────────────────

def test_get_one(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="F1", name="Get Me")
    res = client.get(f"/api/v1/activity-types/{created['id']}", headers=h)
    assert res.status_code == 200
    assert res.json()["code"] == "F1"


def test_get_not_found(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    import uuid
    res = client.get(f"/api/v1/activity-types/{uuid.uuid4()}", headers=h)
    assert res.status_code == 404


# ── update ───────────────────────────────────────────────────────────────────

def test_update_name(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="G1", name="Old Name")
    res = client.patch(
        f"/api/v1/activity-types/{created['id']}",
        json={"name": "New Name"},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["name"] == "New Name"
    assert res.json()["code"] == "G1"  # code unchanged


def test_update_category(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="G2", name="Change Cat", category="GENERAL")
    res = client.patch(
        f"/api/v1/activity-types/{created['id']}",
        json={"category": "TAG_ESTIMATION"},
        headers=h,
    )
    assert res.status_code == 200
    assert res.json()["category"] == "TAG_ESTIMATION"


# ── deactivate ───────────────────────────────────────────────────────────────

def test_deactivate(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    created = _create(client, h, code="H1", name="To Deactivate")
    res = client.delete(f"/api/v1/activity-types/{created['id']}", headers=h)
    assert res.status_code == 200
    assert res.json()["is_active"] is False

    # Not in active-only list
    list_res = client.get("/api/v1/activity-types", headers=h)
    codes = [r["code"] for r in list_res.json()["items"]]
    assert "H1" not in codes


def test_non_admin_cannot_deactivate(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    created = _create(client, h_admin, code="H2", name="Protected")

    h_emp = auth_header(email="emp2@x.com", role=UserRole.employee)
    res = client.delete(f"/api/v1/activity-types/{created['id']}", headers=h_emp)
    assert res.status_code == 403


# ── unauthenticated ──────────────────────────────────────────────────────────

def test_list_unauthenticated(client):
    res = client.get("/api/v1/activity-types")
    assert res.status_code == 401
