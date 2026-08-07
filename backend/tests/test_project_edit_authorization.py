"""PATCH /projects/{id} — who may edit project information.

  PM                     -> every project
  assigned project Head  -> only the projects they Head
  everyone else          -> 403

Head authority is per-project: heading project A must grant nothing on project
B. Create / archive / delete and Head assignment stay PM-only and are asserted
here too, so widening edit access can never silently widen them.
"""
import uuid

import pytest

from app.modules.projects.models import Project, ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/projects"


@pytest.fixture()
def head_login(db, client, make_user, make_employee):
    """Create a user + linked employee, make them Head of `project`, and return
    the auth header. The employee link is what authz resolves the caller by."""

    def _make(email: str, project: Project, *, employee_code: str) -> dict:
        user = make_user(email, "password123", UserRole.employee)
        emp = make_employee(employee_code=employee_code, user_id=user.id)
        project.head_employee_id = emp.id
        db.add(project)
        db.commit()
        res = client.post(
            "/api/v1/auth/login", json={"identifier": email, "password": "password123"}
        )
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _make


# ---------- PM ----------
def test_pm_can_edit_any_project(client, auth_header, make_project):
    pm = auth_header("pm@x.com", role=UserRole.project_manager)
    a = make_project(code="EA-1", status=ProjectStatus.active)
    b = make_project(code="EA-2", status=ProjectStatus.active)
    for p in (a, b):
        res = client.patch(f"{BASE}/{p.id}", headers=pm, json={"client": "New Co"})
        assert res.status_code == 200, res.text
        assert res.json()["client"] == "New Co"


# ---------- assigned Head ----------
def test_assigned_head_can_edit_their_project(client, head_login, make_project):
    project = make_project(code="EA-10", status=ProjectStatus.active)
    head = head_login("head1@x.com", project, employee_code="EH-10")

    res = client.patch(f"{BASE}/{project.id}", headers=head, json={"client": "Head Co"})
    assert res.status_code == 200, res.text
    assert res.json()["client"] == "Head Co"


def test_assigned_head_can_set_scope_type_on_their_project(
    client, head_login, make_project
):
    project = make_project(code="EA-11", status=ProjectStatus.active)
    head = head_login("head2@x.com", project, employee_code="EH-11")

    res = client.patch(
        f"{BASE}/{project.id}", headers=head, json={"scope_type": "TAG_BASED"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "TAG_BASED"


# ---------- Head of a DIFFERENT project ----------
def test_head_of_another_project_is_forbidden(client, head_login, make_project):
    """The core rule: Head is project-specific, never a global edit grant."""
    mine = make_project(code="EA-20", status=ProjectStatus.active)
    other = make_project(code="EA-21", status=ProjectStatus.active)
    head = head_login("head3@x.com", mine, employee_code="EH-20")

    assert client.patch(f"{BASE}/{mine.id}", headers=head, json={"client": "ok"}).status_code == 200
    res = client.patch(f"{BASE}/{other.id}", headers=head, json={"client": "nope"})
    assert res.status_code == 403


def test_forbidden_edit_changes_nothing(db, client, head_login, make_project):
    mine = make_project(code="EA-22", status=ProjectStatus.active)
    other = make_project(code="EA-23", name="Untouched", status=ProjectStatus.active)
    head = head_login("head4@x.com", mine, employee_code="EH-22")

    client.patch(f"{BASE}/{other.id}", headers=head, json={"name": "Hacked"})
    db.expire_all()
    assert db.get(Project, other.id).name == "Untouched"


# ---------- ordinary members / employees ----------
def test_plain_employee_cannot_edit(client, auth_header, make_project):
    emp = auth_header("emp@x.com", role=UserRole.employee)
    project = make_project(code="EA-30", status=ProjectStatus.active)
    assert client.patch(f"{BASE}/{project.id}", headers=emp, json={"client": "x"}).status_code == 403


def test_project_member_cannot_edit(
    client, auth_header, make_user, make_employee, make_project, make_project_member
):
    """A Contributor on the project can VIEW it but must not be able to edit."""
    user = make_user("member@x.com", "password123", UserRole.employee)
    emp = make_employee(employee_code="EM-30", user_id=user.id)
    project = make_project(code="EA-31", status=ProjectStatus.active)
    make_project_member(project_id=project.id, employee_id=emp.id)

    res = client.post(
        "/api/v1/auth/login", json={"identifier": "member@x.com", "password": "password123"}
    )
    h = {"Authorization": f"Bearer {res.json()['access_token']}"}

    assert client.get(f"{BASE}/{project.id}", headers=h).status_code == 200   # can view
    assert client.patch(f"{BASE}/{project.id}", headers=h, json={"client": "x"}).status_code == 403


# ---------- create / archive / head assignment stay PM-only ----------
def test_head_cannot_create_a_project(client, head_login, make_project):
    project = make_project(code="EA-40", status=ProjectStatus.active)
    head = head_login("head5@x.com", project, employee_code="EH-40")
    res = client.post(BASE, headers=head, json={"code": "EA-NEW", "name": "New"})
    assert res.status_code == 403


def test_head_cannot_archive_their_project(client, head_login, make_project):
    project = make_project(code="EA-41", status=ProjectStatus.active)
    head = head_login("head6@x.com", project, employee_code="EH-41")
    assert client.delete(f"{BASE}/{project.id}", headers=head).status_code == 403


def test_head_cannot_reassign_the_head(client, head_login, make_project, make_employee):
    project = make_project(code="EA-42", status=ProjectStatus.active)
    head = head_login("head7@x.com", project, employee_code="EH-42")
    other = make_employee(employee_code="EH-43")
    res = client.put(
        f"{BASE}/{project.id}/head", headers=head, json={"head_employee_id": str(other.id)}
    )
    assert res.status_code == 403


# ---------- unchanged behaviour ----------
def test_unknown_project_is_404_not_403(client, auth_header):
    pm = auth_header("pm2@x.com", role=UserRole.project_manager)
    res = client.patch(f"{BASE}/{uuid.uuid4()}", headers=pm, json={"client": "x"})
    assert res.status_code == 404


def test_unauthenticated_edit_is_401(client, make_project):
    project = make_project(code="EA-50", status=ProjectStatus.active)
    assert client.patch(f"{BASE}/{project.id}", json={"client": "x"}).status_code == 401
