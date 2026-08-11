"""Project scope type (Phase 2) — classification only.

projects.scope_type says whether a project takes part in Project Tag Scope
functionality (TAG_BASED) or not (NONE). This phase adds the classification and
nothing else: no tag counts, no validation, no calculation reads it. These tests
pin the default, both reclassification directions, the enum rejection and the
API contract, plus the compatibility guarantees for callers that never send the
field.
"""
import uuid

from app.modules.projects.models import Project, ProjectStatus
from app.modules.users.models import UserRole


def _payload(**over):
    base = {"code": "SCOPE-001", "name": "Apollo", "client": "ACME"}
    base.update(over)
    return base


# ---------- default ----------
def test_create_without_scope_type_defaults_to_none(client, auth_header):
    """Test 1 — a client that never heard of scope_type gets a normal project."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/projects", headers=h, json=_payload())
    assert res.status_code == 201, res.text
    assert res.json()["scope_type"] == "NONE"


def test_row_created_outside_the_api_defaults_to_none(client, auth_header, make_project):
    """The column's server default covers the import / seed / fixture paths that
    build a Project directly and never mention scope_type."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-DIRECT", status=ProjectStatus.active)
    assert p.scope_type == "NONE"
    assert client.get(f"/api/v1/projects/{p.id}", headers=h).json()["scope_type"] == "NONE"


# ---------- create ----------
def test_create_tag_based_project(client, auth_header):
    """Test 2."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post(
        "/api/v1/projects", headers=h, json=_payload(scope_type="TAG_BASED")
    )
    assert res.status_code == 201, res.text
    assert res.json()["scope_type"] == "TAG_BASED"


def test_create_explicit_none(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/projects", headers=h, json=_payload(scope_type="NONE"))
    assert res.status_code == 201, res.text
    assert res.json()["scope_type"] == "NONE"


# ---------- update ----------
def test_update_none_to_tag_based(client, auth_header, make_project):
    """Test 3 — every existing project starts NONE and must be promotable."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-P1", status=ProjectStatus.active)
    res = client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "TAG_BASED"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "TAG_BASED"
    # Persisted, not just echoed back.
    assert client.get(f"/api/v1/projects/{p.id}", headers=h).json()["scope_type"] == "TAG_BASED"


def test_update_tag_based_back_to_none(client, auth_header, make_project):
    """Test 4 — allowed in this phase: no tag-scope records exist yet."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-P2", status=ProjectStatus.active)
    assert client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "TAG_BASED"}
    ).status_code == 200
    res = client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "NONE"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "NONE"


def test_update_without_scope_type_leaves_it_unchanged(client, auth_header, make_project):
    """An edit of unrelated fields must never silently reclassify a project."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-P3", status=ProjectStatus.active)
    client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "TAG_BASED"})
    res = client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"client": "New Co"})
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "TAG_BASED"


def test_update_with_explicit_null_leaves_it_unchanged(client, auth_header, make_project):
    """A NOT NULL column must not be clearable by an older client that sends the
    whole object with scope_type: null."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-P4", status=ProjectStatus.active)
    client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "TAG_BASED"})
    res = client.patch(f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": None})
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "TAG_BASED"


# ---------- validation ----------
def test_invalid_scope_type_rejected_on_create(client, auth_header):
    """Test 5."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/projects", headers=h, json=_payload(scope_type="RANDOM"))
    assert res.status_code == 422


def test_invalid_scope_type_rejected_on_update(client, auth_header, make_project, db):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-P5", status=ProjectStatus.active)
    res = client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "RANDOM"}
    )
    assert res.status_code == 422
    # Nothing stored.
    db.expire_all()
    assert db.get(Project, p.id).scope_type == "NONE"


def test_lowercase_value_rejected(client, auth_header):
    """Stored values are uppercase; a near-miss must not be coerced through."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.post("/api/v1/projects", headers=h, json=_payload(scope_type="tag_based"))
    assert res.status_code == 422


# ---------- API contract ----------
def test_detail_and_list_expose_scope_type(client, auth_header):
    """Test 6 — the Project Detail page reads project.scope_type from here."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    created = client.post(
        "/api/v1/projects", headers=h, json=_payload(scope_type="TAG_BASED")
    ).json()

    detail = client.get(f"/api/v1/projects/{created['id']}", headers=h)
    assert detail.status_code == 200
    assert detail.json()["scope_type"] == "TAG_BASED"

    listed = client.get("/api/v1/projects", headers=h).json()["items"]
    row = next(i for i in listed if i["id"] == created["id"])
    assert row["scope_type"] == "TAG_BASED"


# ---------- regression ----------
def test_none_project_behaves_exactly_as_before(client, auth_header, make_project):
    """Test 11 — a NONE project keeps working with no extra scope requirement:
    it lists, reads, edits and archives with the field never mentioned."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    p = make_project(code="SCOPE-REG", status=ProjectStatus.planning)

    assert client.get(f"/api/v1/projects/{p.id}", headers=h).status_code == 200
    assert client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"status": "active"}
    ).status_code == 200
    assert client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"name": "Renamed"}
    ).status_code == 200
    assert client.delete(f"/api/v1/projects/{p.id}", headers=h).status_code == 204


def test_tag_based_project_adds_no_new_requirements(client, auth_header):
    """Classifying a project TAG_BASED changes nothing about how it is edited —
    no tag count is demanded anywhere in this phase."""
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    created = client.post(
        "/api/v1/projects", headers=h, json=_payload(scope_type="TAG_BASED")
    ).json()
    res = client.patch(
        f"/api/v1/projects/{created['id']}", headers=h, json={"status": "active"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "TAG_BASED"


# ---------- permissions ----------
def test_employee_cannot_set_scope_type(client, auth_header, make_project):
    """No new RBAC: setting scope_type rides on the existing project-edit
    permission, which an employee does not have."""
    h = auth_header("emp@example.com", role=UserRole.employee)
    p = make_project(code="SCOPE-RBAC", status=ProjectStatus.active)
    res = client.patch(
        f"/api/v1/projects/{p.id}", headers=h, json={"scope_type": "TAG_BASED"}
    )
    assert res.status_code == 403


def test_unknown_project_still_404(client, auth_header):
    h = auth_header("admin@example.com", role=UserRole.project_manager)
    res = client.patch(
        f"/api/v1/projects/{uuid.uuid4()}", headers=h, json={"scope_type": "TAG_BASED"}
    )
    assert res.status_code == 404
