"""Tests for the activity_master module: hierarchy, benchmark validation, RBAC."""
import uuid

from app.modules.users.models import UserRole

BASE = "/api/v1/activity-master"


def _create_activity(client, headers, name="Test Activity", **kwargs) -> dict:
    payload = {"name": name}
    payload.update(kwargs)
    res = client.post(f"{BASE}/activities", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def _create_sub(client, headers, activity_id, name="Test Sub", **kwargs) -> dict:
    payload = {"name": name}
    payload.update(kwargs)
    res = client.post(f"{BASE}/activities/{activity_id}/sub-activities", json=payload, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ── Activity CRUD ────────────────────────────────────────────────────────────

def test_admin_can_create_activity(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    data = _create_activity(client, h, name="FMTL", code="FMTL")
    assert data["level"] == "activity"
    assert data["parent_id"] is None
    assert data["is_active"] is True


def test_non_admin_cannot_create_activity(client, auth_header):
    h = auth_header(email="emp@x.com", role=UserRole.employee)
    res = client.post(f"{BASE}/activities", json={"name": "FMTL"}, headers=h)
    assert res.status_code == 403


def test_list_activities_default_active_only(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="Visible")
    client.delete(f"{BASE}/activities/{a['id']}", headers=h)
    res = client.get(f"{BASE}/activities", headers=h)
    names = [r["name"] for r in res.json()]
    assert "Visible" not in names


def test_employee_can_list_activities(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    _create_activity(client, h_admin, name="Listed")
    h_emp = auth_header(email="emp2@x.com", role=UserRole.employee)
    res = client.get(f"{BASE}/activities", headers=h_emp)
    assert res.status_code == 200


# ── Sub-Activity CRUD + hierarchy rules ─────────────────────────────────────

def test_create_sub_activity_under_activity(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    sub = _create_sub(client, h, a["id"], name="FMTL-REWORK", benchmark_type="NUMERIC", benchmark_value=250,
                       relevant_count_field="tags")
    assert sub["level"] == "sub_activity"
    assert sub["parent_id"] == a["id"]
    assert sub["benchmark_type"] == "NUMERIC"
    assert float(sub["benchmark_value"]) == 250.0
    assert sub["relevant_count_field"] == "tags"


def test_numeric_without_value_rejected(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    res = client.post(
        f"{BASE}/activities/{a['id']}/sub-activities",
        json={"name": "Bad", "benchmark_type": "NUMERIC", "relevant_count_field": "tags"},
        headers=h,
    )
    assert res.status_code == 422


def test_numeric_without_count_field_rejected(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    res = client.post(
        f"{BASE}/activities/{a['id']}/sub-activities",
        json={"name": "Bad", "benchmark_type": "NUMERIC", "benchmark_value": 250},
        headers=h,
    )
    assert res.status_code == 422


def test_task_based_needs_no_value(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="DOC IDB")
    sub = _create_sub(client, h, a["id"], name="DOC IDB-AUDIT QUERY", benchmark_type="TASK_BASED")
    assert sub["benchmark_type"] == "TASK_BASED"
    assert sub["benchmark_value"] is None


def test_create_sub_activity_under_nonexistent_activity_404(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    res = client.post(
        f"{BASE}/activities/{uuid.uuid4()}/sub-activities",
        json={"name": "Orphan"},
        headers=h,
    )
    assert res.status_code == 404


def test_create_sub_activity_under_a_sub_activity_rejected(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    sub = _create_sub(client, h, a["id"], name="FMTL-REWORK")
    res = client.post(
        f"{BASE}/activities/{sub['id']}/sub-activities",
        json={"name": "Nested"},
        headers=h,
    )
    assert res.status_code == 422


def test_list_sub_activities_under_activity(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="MTL")
    _create_sub(client, h, a["id"], name="MTL-QC", benchmark_type="NUMERIC", benchmark_value=500,
                relevant_count_field="tags")
    _create_sub(client, h, a["id"], name="MTL-REWORK", benchmark_type="NUMERIC", benchmark_value=200,
                relevant_count_field="tags")
    res = client.get(f"{BASE}/activities/{a['id']}/sub-activities", headers=h)
    names = {r["name"] for r in res.json()}
    assert names == {"MTL-QC", "MTL-REWORK"}


def test_flat_sub_activities_includes_activity_name(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="BOM IDB")
    sub = _create_sub(client, h, a["id"], name="BOM IDB-QC", benchmark_type="NUMERIC", benchmark_value=500,
                       relevant_count_field="spares")
    res = client.get(f"{BASE}/sub-activities", headers=h)
    rows = {r["id"]: r for r in res.json()}
    assert sub["id"] in rows
    assert rows[sub["id"]]["activity_id"] == a["id"]
    assert rows[sub["id"]]["activity_name"] == "BOM IDB"
    assert rows[sub["id"]]["relevant_count_field"] == "spares"


# ── update ───────────────────────────────────────────────────────────────────

def test_update_sub_activity_benchmark(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    sub = _create_sub(client, h, a["id"], name="FMTL-REWORK", benchmark_type="NUMERIC", benchmark_value=250,
                       relevant_count_field="tags")
    res = client.patch(
        f"{BASE}/sub-activities/{sub['id']}", json={"benchmark_value": 300}, headers=h
    )
    assert res.status_code == 200
    assert float(res.json()["benchmark_value"]) == 300.0


def test_update_to_numeric_without_count_field_rejected(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    sub = _create_sub(client, h, a["id"], name="FMTL-AUDIT", benchmark_type="TASK_BASED")
    res = client.patch(
        f"{BASE}/sub-activities/{sub['id']}",
        json={"benchmark_type": "NUMERIC", "benchmark_value": 250},
        headers=h,
    )
    assert res.status_code == 422


def test_update_activity_rejects_benchmark_fields(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    res = client.patch(
        f"{BASE}/activities/{a['id']}", json={"benchmark_type": "NUMERIC", "benchmark_value": 1}, headers=h
    )
    assert res.status_code == 422


# ── deactivate ───────────────────────────────────────────────────────────────

def test_deactivate_sub_activity_does_not_cascade(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h, name="FMTL")
    sub = _create_sub(client, h, a["id"], name="FMTL-REWORK")
    client.delete(f"{BASE}/sub-activities/{sub['id']}", headers=h)

    # Activity itself is untouched.
    res = client.get(f"{BASE}/activities", headers=h)
    names = [r["name"] for r in res.json()]
    assert "FMTL" in names


def test_non_admin_cannot_deactivate(client, auth_header):
    h_admin = auth_header(role=UserRole.project_manager)
    a = _create_activity(client, h_admin, name="FMTL")
    h_emp = auth_header(email="emp3@x.com", role=UserRole.employee)
    res = client.delete(f"{BASE}/activities/{a['id']}", headers=h_emp)
    assert res.status_code == 403


def test_list_unauthenticated(client):
    res = client.get(f"{BASE}/activities")
    assert res.status_code == 401
