"""API tests for the projects module: CRUD, transitions, membership, RBAC."""
import uuid

from app.modules.employees.models import EmployeeStatus
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole


def _payload(**over):
    base = {"code": "PRJ-001", "name": "Apollo", "client": "ACME"}
    base.update(over)
    return base


# ---------- admin CRUD ----------
def test_admin_create_and_get(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.post("/api/v1/projects", headers=h, json=_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "planning"
    assert body["member_count"] == 0

    got = client.get(f"/api/v1/projects/{body['id']}", headers=h)
    assert got.status_code == 200
    assert got.json()["code"] == "PRJ-001"


def test_create_duplicate_code_409(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    assert client.post("/api/v1/projects", headers=h, json=_payload()).status_code == 201
    assert client.post("/api/v1/projects", headers=h, json=_payload(name="X")).status_code == 409


def test_create_missing_name_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    assert client.post("/api/v1/projects", headers=h, json={"code": "P"}).status_code == 422


def test_create_bad_dates_422(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    res = client.post(
        "/api/v1/projects",
        headers=h,
        json=_payload(start_date="2026-05-10", end_date="2026-05-01"),
    )
    assert res.status_code == 422


def test_update_status_valid(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="P-1", status=ProjectStatus.planning)
    res = client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"status": "active"})
    assert res.status_code == 200
    assert res.json()["status"] == "active"


def test_patch_to_archived_rejected(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="P-2", status=ProjectStatus.planning)
    res = client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"status": "archived"})
    assert res.status_code == 422


def test_invalid_transition_rejected(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="P-3", status=ProjectStatus.completed)
    # completed -> on_hold is not allowed (only -> active)
    res = client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"status": "on_hold"})
    assert res.status_code == 422


def test_archive_hides_from_default_list(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="P-4", status=ProjectStatus.active)
    assert client.delete(f"/api/v1/projects/{p.id}", headers=h).status_code == 204
    default = client.get("/api/v1/projects", headers=h).json()
    assert all(item["id"] != str(p.id) for item in default["items"])
    archived = client.get("/api/v1/projects?status=archived", headers=h).json()
    assert any(item["id"] == str(p.id) for item in archived["items"])
    assert client.get(f"/api/v1/projects/{p.id}", headers=h).json()["status"] == "archived"


def test_get_unknown_404(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.admin)
    assert client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=h).status_code == 404


# ---------- list / search / filter ----------
def test_list_pagination(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    for i in range(3):
        make_project(code=f"C-{i}", name=f"Proj{i}")
    page = client.get("/api/v1/projects?limit=2", headers=h).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_search_by_name(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    make_project(code="C-a", name="Alpha")
    make_project(code="C-b", name="Beta")
    res = client.get("/api/v1/projects?q=alph", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["name"] == "Alpha"


def test_filter_by_status(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    make_project(code="C-on", status=ProjectStatus.on_hold)
    make_project(code="C-pl", status=ProjectStatus.planning)
    res = client.get("/api/v1/projects?status=on_hold", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["status"] == "on_hold"


# ---------- membership ----------
def test_assign_and_list_member(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-1")
    e = make_employee(employee_code="E-1", first_name="Ada", last_name="Lovelace")
    res = client.post(
        f"/api/v1/projects/{p.id}/members",
        headers=h,
        json={"employee_id": str(e.id), "role": "lead"},
    )
    assert res.status_code == 201, res.text
    assert res.json()["employee_name"] == "Ada Lovelace"
    assert res.json()["role"] == "lead"

    members = client.get(f"/api/v1/projects/{p.id}/members", headers=h).json()
    assert len(members) == 1
    assert client.get(f"/api/v1/projects/{p.id}", headers=h).json()["member_count"] == 1


def test_duplicate_assignment_409(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-2")
    e = make_employee(employee_code="E-2")
    body = {"employee_id": str(e.id), "role": "member"}
    assert client.post(f"/api/v1/projects/{p.id}/members", headers=h, json=body).status_code == 201
    assert client.post(f"/api/v1/projects/{p.id}/members", headers=h, json=body).status_code == 409


def test_assign_unknown_employee_422(client, auth_header, make_project):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-3")
    res = client.post(
        f"/api/v1/projects/{p.id}/members",
        headers=h,
        json={"employee_id": str(uuid.uuid4()), "role": "member"},
    )
    assert res.status_code == 422


def test_assign_inactive_employee_422(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-4")
    e = make_employee(employee_code="E-4", status=EmployeeStatus.exited)
    res = client.post(
        f"/api/v1/projects/{p.id}/members",
        headers=h,
        json={"employee_id": str(e.id)},
    )
    assert res.status_code == 422


def test_assign_to_archived_project_422(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-5", status=ProjectStatus.archived)
    e = make_employee(employee_code="E-5")
    res = client.post(
        f"/api/v1/projects/{p.id}/members", headers=h, json={"employee_id": str(e.id)}
    )
    assert res.status_code == 422


def test_single_lead_enforced(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-6")
    e1 = make_employee(employee_code="E-6a")
    e2 = make_employee(employee_code="E-6b")
    client.post(f"/api/v1/projects/{p.id}/members", headers=h, json={"employee_id": str(e1.id), "role": "lead"})
    client.post(f"/api/v1/projects/{p.id}/members", headers=h, json={"employee_id": str(e2.id), "role": "lead"})
    members = client.get(f"/api/v1/projects/{p.id}/members", headers=h).json()
    leads = [m for m in members if m["role"] == "lead"]
    assert len(leads) == 1
    assert leads[0]["employee_id"] == str(e2.id)


def test_unassign_member(client, auth_header, make_project, make_employee):
    h = auth_header("admin@example.com", role=UserRole.admin)
    p = make_project(code="M-7")
    e = make_employee(employee_code="E-7")
    client.post(f"/api/v1/projects/{p.id}/members", headers=h, json={"employee_id": str(e.id)})
    assert client.delete(f"/api/v1/projects/{p.id}/members/{e.id}", headers=h).status_code == 204
    assert client.get(f"/api/v1/projects/{p.id}/members", headers=h).json() == []


# ---------- RBAC ----------
def test_viewer_reads_cannot_create(client, auth_header, make_project):
    make_project(code="V-1")
    h = auth_header("viewer@example.com", role=UserRole.viewer)
    assert client.get("/api/v1/projects", headers=h).status_code == 200
    assert client.post("/api/v1/projects", headers=h, json=_payload(code="V-X")).status_code == 403


def test_employee_sees_only_assigned(
    client, make_user, make_employee, make_project, make_project_member, login
):
    user = make_user("emp@example.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=user.id)
    assigned = make_project(code="ASSIGNED", status=ProjectStatus.active)
    make_project(code="OTHER", status=ProjectStatus.active)
    make_project_member(project_id=assigned.id, employee_id=emp.id)
    h = login("emp@example.com")
    res = client.get("/api/v1/projects", headers=h).json()
    assert {p["code"] for p in res["items"]} == {"ASSIGNED"}


def test_employee_cannot_view_unassigned_403(
    client, make_user, make_employee, make_project, login
):
    user = make_user("emp@example.com", role=UserRole.employee)
    make_employee(employee_code="EMP", user_id=user.id)
    other = make_project(code="OTHER")
    h = login("emp@example.com")
    assert client.get(f"/api/v1/projects/{other.id}", headers=h).status_code == 403


def test_manager_scoped_to_assigned(
    client, make_user, make_employee, make_project, make_project_member, login
):
    user = make_user("mgr@example.com", role=UserRole.manager)
    emp = make_employee(employee_code="MGR", user_id=user.id)
    assigned = make_project(code="MGR-ASSIGNED", status=ProjectStatus.active)
    make_project(code="MGR-OTHER", status=ProjectStatus.active)
    make_project_member(project_id=assigned.id, employee_id=emp.id)
    h = login("mgr@example.com")
    res = client.get("/api/v1/projects", headers=h).json()
    assert {p["code"] for p in res["items"]} == {"MGR-ASSIGNED"}
    assert client.post("/api/v1/projects", headers=h, json=_payload(code="MGR-NEW")).status_code == 403
