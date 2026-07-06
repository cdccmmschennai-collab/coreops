"""PUT /projects/{id}/head — PM assigns/replaces/clears the project Head.

Covers: the head column is set + returned with the head's name; the Head is
auto-added to project_members (visibility backbone); a timeline event is emitted
(head_assigned first time, head_changed on replace/clear); the prior Head's
member row is left in place; non-PM is forbidden; an inactive employee is rejected.
"""
from app.modules.employees.models import EmployeeStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/projects"


def _member_ids(client, headers, project_id):
    return {m["employee_id"] for m in client.get(f"{BASE}/{project_id}/members", headers=headers).json()}


def _event_types(client, headers, project_id):
    return [e["event_type"] for e in client.get(f"{BASE}/{project_id}/timeline", headers=headers).json()]


def test_pm_assigns_head_sets_column_member_and_timeline(
    client, auth_header, make_project, make_employee
):
    pm = auth_header("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="HD-1")
    emp = make_employee(employee_code="EH-1", first_name="Head", last_name="One")

    resp = client.put(f"{BASE}/{project.id}/head", headers=pm,
                      json={"head_employee_id": str(emp.id)})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["head_employee_id"] == str(emp.id)
    assert body["head_employee_name"] == "Head One"

    assert str(emp.id) in _member_ids(client, pm, project.id)
    assert "head_assigned" in _event_types(client, pm, project.id)


def test_replace_head_emits_changed_and_keeps_prior_member(
    client, auth_header, make_project, make_employee
):
    pm = auth_header("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="HD-2")
    a = make_employee(employee_code="EA")
    b = make_employee(employee_code="EB")

    client.put(f"{BASE}/{project.id}/head", headers=pm, json={"head_employee_id": str(a.id)})
    resp = client.put(f"{BASE}/{project.id}/head", headers=pm, json={"head_employee_id": str(b.id)})
    assert resp.status_code == 200, resp.text
    assert resp.json()["head_employee_id"] == str(b.id)

    members = _member_ids(client, pm, project.id)
    assert str(a.id) in members and str(b.id) in members  # prior Head's row retained
    types = _event_types(client, pm, project.id)
    assert "head_assigned" in types and "head_changed" in types


def test_clear_head_sets_null_and_emits_changed(
    client, auth_header, make_project, make_employee
):
    pm = auth_header("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="HD-3")
    emp = make_employee(employee_code="EC")

    client.put(f"{BASE}/{project.id}/head", headers=pm, json={"head_employee_id": str(emp.id)})
    resp = client.put(f"{BASE}/{project.id}/head", headers=pm, json={"head_employee_id": None})
    assert resp.status_code == 200, resp.text
    assert resp.json()["head_employee_id"] is None
    assert "head_changed" in _event_types(client, pm, project.id)


def test_non_pm_cannot_assign_head(client, auth_header, make_project, make_employee):
    emp_hdr = auth_header("e@x.com", role=UserRole.employee)
    project = make_project(code="HD-4")
    emp = make_employee(employee_code="ED")

    resp = client.put(f"{BASE}/{project.id}/head", headers=emp_hdr,
                      json={"head_employee_id": str(emp.id)})
    assert resp.status_code == 403, resp.text


def test_inactive_employee_rejected(client, auth_header, make_project, make_employee):
    pm = auth_header("pm@x.com", role=UserRole.project_manager)
    project = make_project(code="HD-5")
    emp = make_employee(employee_code="EE", status=EmployeeStatus.exited)

    resp = client.put(f"{BASE}/{project.id}/head", headers=pm,
                      json={"head_employee_id": str(emp.id)})
    assert resp.status_code == 422, resp.text
