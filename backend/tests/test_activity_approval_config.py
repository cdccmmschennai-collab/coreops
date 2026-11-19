"""Rework Activity Approval - Phase 1: the Approval Activities configuration
(migration 0090, activity_master.requires_pm_approval)."""
from app.modules.users.models import UserRole

BASE = "/api/v1/activity-master"


def _activity(client, h, name="INSTRUMENT ENGINEERING") -> dict:
    res = client.post(f"{BASE}/activities", json={"name": name}, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


def _sub(client, h, activity_id, name) -> dict:
    res = client.post(
        f"{BASE}/activities/{activity_id}/sub-activities", json={"name": name}, headers=h
    )
    assert res.status_code == 201, res.text
    return res.json()


def _set(client, h, sub_id, value: bool):
    return client.put(
        f"{BASE}/sub-activities/{sub_id}/approval",
        json={"requires_pm_approval": value},
        headers=h,
    )


def test_new_sub_activity_does_not_require_approval(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    sub = _sub(client, h, a["id"], "Instrument Rework")
    # "Rework" in the name is only a search hint - never automatic approval.
    assert sub["requires_pm_approval"] is False
    assert client.get(f"{BASE}/approval-activities", headers=h).json() == []


def test_add_and_list_with_parent_name(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    rework = _sub(client, h, a["id"], "Instrument Rework")
    _sub(client, h, a["id"], "Instrument Design")

    res = _set(client, h, rework["id"], True)
    assert res.status_code == 200, res.text
    assert res.json()["activity_name"] == "INSTRUMENT ENGINEERING"

    listed = client.get(f"{BASE}/approval-activities", headers=h).json()
    assert [r["name"] for r in listed] == ["Instrument Rework"]
    assert listed[0]["activity_name"] == "INSTRUMENT ENGINEERING"

    # The flag reaches the report form's sub-activity dropdown.
    flat = {r["name"]: r for r in client.get(f"{BASE}/sub-activities", headers=h).json()}
    assert flat["Instrument Rework"]["requires_pm_approval"] is True
    assert flat["Instrument Design"]["requires_pm_approval"] is False


def test_adding_twice_never_duplicates(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    rework = _sub(client, h, a["id"], "Cable Rework")
    assert _set(client, h, rework["id"], True).status_code == 200
    assert _set(client, h, rework["id"], True).status_code == 200
    assert len(client.get(f"{BASE}/approval-activities", headers=h).json()) == 1


def test_remove_from_list(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    rework = _sub(client, h, a["id"], "Drawing Rework")
    _set(client, h, rework["id"], True)
    assert _set(client, h, rework["id"], False).status_code == 200
    assert client.get(f"{BASE}/approval-activities", headers=h).json() == []


def test_parent_activity_cannot_be_configured(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    _sub(client, h, a["id"], "Instrument Rework")
    res = _set(client, h, a["id"], True)
    assert res.status_code == 422
    # And nothing under it was flagged as a side effect.
    assert client.get(f"{BASE}/approval-activities", headers=h).json() == []


def test_employee_cannot_configure_or_list(client, auth_header):
    h_pm = auth_header(role=UserRole.project_manager)
    a = _activity(client, h_pm)
    rework = _sub(client, h_pm, a["id"], "Instrument Rework")
    h_emp = auth_header(email="emp@x.com", role=UserRole.employee)
    assert _set(client, h_emp, rework["id"], True).status_code == 403
    assert client.get(f"{BASE}/approval-activities", headers=h_emp).status_code == 403


def test_deactivated_sub_stays_visible_for_removal(client, auth_header):
    h = auth_header(role=UserRole.project_manager)
    a = _activity(client, h)
    rework = _sub(client, h, a["id"], "Old Rework")
    _set(client, h, rework["id"], True)
    client.delete(f"{BASE}/sub-activities/{rework['id']}", headers=h)
    listed = client.get(f"{BASE}/approval-activities", headers=h).json()
    assert listed and listed[0]["is_active"] is False
