"""Project tag scope (Phase 3) — data foundation.

Covers the schema (columns, defaults, CHECKs, per-project revision uniqueness),
the revision-recording service primitive, the read endpoint and its PM/Head
permission, and the guard that stops TAG_BASED -> NONE from destroying history.

No progress is computed anywhere in this phase, and nothing reads Daily
Reports, benchmarks or Activity Master — see test_tag_scope_reads_no_report_data.
"""
import uuid

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.modules.projects import service
from app.modules.projects.models import Project, ProjectStatus, ProjectTagScopeRevision
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

BASE = "/api/v1/projects"


@pytest.fixture()
def pm_user(db, make_user):
    return make_user("scopepm@x.com", "password123", UserRole.project_manager)


@pytest.fixture()
def tag_project(db, make_project):
    """A TAG_BASED project with no scope established yet."""
    p = make_project(code="TS-BASE", status=ProjectStatus.active)
    p.scope_type = "TAG_BASED"
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def head_login(db, client, make_user, make_employee):
    def _make(email: str, project: Project, *, employee_code: str) -> dict:
        user = make_user(email, "password123", UserRole.employee)
        emp = make_employee(employee_code=employee_code, user_id=user.id)
        project.head_employee_id = emp.id
        db.add(project)
        db.commit()
        res = client.post(
            "/api/v1/auth/login", json={"identifier": email, "password": "password123"}
        )
        return {"Authorization": f"Bearer {res.json()['access_token']}"}

    return _make


# ---------- migration / schema ----------
def test_new_project_scope_columns_exist(db):
    cols = {c["name"] for c in inspect(db.get_bind()).get_columns("projects")}
    assert {
        "estimated_tag_count",
        "tag_scope_status",
        "tag_scope_revision",
        "tag_scope_updated_at",
        "tag_scope_updated_by",
    } <= cols


def test_history_table_exists_with_expected_columns(db):
    insp = inspect(db.get_bind())
    assert "project_tag_scope_revisions" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("project_tag_scope_revisions")}
    assert {
        "id",
        "project_id",
        "revision",
        "previous_estimated_tag_count",
        "new_estimated_tag_count",
        "previous_status",
        "new_status",
        "reason",
        "changed_by",
        "created_at",
    } <= cols


def test_project_revision_pair_is_unique(db):
    uqs = {
        u["name"]
        for u in inspect(db.get_bind()).get_unique_constraints("project_tag_scope_revisions")
    }
    assert "project_tag_scope_revisions_uq" in uqs


def test_positive_count_check_exists(db):
    checks = {
        c["name"] for c in inspect(db.get_bind()).get_check_constraints("projects")
    }
    assert "projects_estimated_tag_count_positive" in checks
    assert "projects_tag_scope_status_valid" in checks


def test_existing_projects_default_to_no_scope(db, make_project):
    """A project created without any scope input — the state every pre-0065 row
    was backfilled to."""
    p = make_project(code="TS-DEFAULT", status=ProjectStatus.active)
    assert p.estimated_tag_count is None
    assert p.tag_scope_status is None
    assert p.tag_scope_revision == 0
    assert p.tag_scope_updated_at is None
    assert p.tag_scope_updated_by is None


def test_zero_and_negative_counts_are_rejected_by_the_database(db, tag_project):
    for bad in (0, -1, -500):
        with pytest.raises(IntegrityError):
            db.execute(
                text("UPDATE projects SET estimated_tag_count = :c WHERE id = :i"),
                {"c": bad, "i": tag_project.id},
            )
            db.flush()
        db.rollback()


def test_unknown_status_is_rejected_by_the_database(db, tag_project):
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE projects SET tag_scope_status = 'NOT_STARTED' WHERE id = :i"),
            {"i": tag_project.id},
        )
        db.flush()
    db.rollback()


def test_duplicate_revision_for_one_project_is_rejected(db, tag_project, pm_user):
    def row(rev: int) -> ProjectTagScopeRevision:
        return ProjectTagScopeRevision(
            project_id=tag_project.id,
            revision=rev,
            previous_estimated_tag_count=None,
            new_estimated_tag_count=100,
            previous_status=None,
            new_status="PROVISIONAL",
            reason="x",
            changed_by=pm_user.id,
        )

    db.add(row(1))
    db.commit()
    db.add(row(1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_same_revision_number_on_two_projects_is_fine(db, make_project, pm_user):
    """Revision numbers are unique per project, never globally."""
    a = make_project(code="TS-U1", status=ProjectStatus.active)
    b = make_project(code="TS-U2", status=ProjectStatus.active)
    for p in (a, b):
        db.add(ProjectTagScopeRevision(
            project_id=p.id, revision=1, new_estimated_tag_count=10,
            new_status="PROVISIONAL", reason="r", changed_by=pm_user.id,
        ))
    db.commit()
    assert db.query(ProjectTagScopeRevision).count() == 2


# ---------- service primitive ----------
def test_first_revision_sets_scope_and_history(db, tag_project, pm_user):
    p = service.record_tag_scope_revision(
        db, pm_user, tag_project.id,
        new_estimated_tag_count=1000, new_status="PROVISIONAL",
        reason="Initial project estimate",
    )
    assert p.estimated_tag_count == 1000
    assert p.tag_scope_status == "PROVISIONAL"
    assert p.tag_scope_revision == 1
    assert p.tag_scope_updated_at is not None
    assert p.tag_scope_updated_by == pm_user.id

    rows = db.query(ProjectTagScopeRevision).all()
    assert len(rows) == 1
    assert rows[0].revision == 1
    assert rows[0].previous_estimated_tag_count is None   # nothing came before
    assert rows[0].previous_status is None
    assert rows[0].new_estimated_tag_count == 1000
    assert rows[0].reason == "Initial project estimate"


def test_revision_chain_preserves_every_previous_value(db, tag_project, pm_user):
    """The worked example: 1,000 provisional -> 2,000 baselined -> 2,500."""
    service.record_tag_scope_revision(
        db, pm_user, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="Initial project estimate")
    service.record_tag_scope_revision(
        db, pm_user, tag_project.id, new_estimated_tag_count=2000,
        new_status="BASELINED", reason="FMTL scope established")
    p = service.record_tag_scope_revision(
        db, pm_user, tag_project.id, new_estimated_tag_count=2500,
        new_status="BASELINED", reason="Additional tags found in new reference documents")

    assert (p.estimated_tag_count, p.tag_scope_status, p.tag_scope_revision) == (
        2500, "BASELINED", 3,
    )
    rows = db.query(ProjectTagScopeRevision).order_by(ProjectTagScopeRevision.revision).all()
    assert [r.revision for r in rows] == [1, 2, 3]
    assert [r.previous_estimated_tag_count for r in rows] == [None, 1000, 2000]
    assert [r.new_estimated_tag_count for r in rows] == [1000, 2000, 2500]
    assert [r.previous_status for r in rows] == [None, "PROVISIONAL", "BASELINED"]
    assert [r.new_status for r in rows] == ["PROVISIONAL", "BASELINED", "BASELINED"]


@pytest.mark.parametrize("bad", [0, -10])
def test_service_rejects_non_positive_counts(db, tag_project, pm_user, bad):
    with pytest.raises(AppError) as e:
        service.record_tag_scope_revision(
            db, pm_user, tag_project.id, new_estimated_tag_count=bad,
            new_status="PROVISIONAL", reason="r")
    assert e.value.status_code == 422
    db.rollback()
    assert db.get(Project, tag_project.id).estimated_tag_count is None


def test_service_rejects_unknown_status(db, tag_project, pm_user):
    with pytest.raises(AppError):
        service.record_tag_scope_revision(
            db, pm_user, tag_project.id, new_estimated_tag_count=10,
            new_status="FINALIZED", reason="r")
    db.rollback()


def test_service_reason_policy_depends_on_whether_a_scope_exists(db, tag_project, pm_user):
    """Blank reason: defaulted on the first estimate, refused on a revision.

    Phase 4 settled this deliberately — "why" is self-evident when a project is
    being set up, but a change to an established number is a decision somebody
    has to account for. (Phase 3 refused both; the write workflow superseded
    that.) The endpoint-level halves live in test_project_tag_scope_write.py.
    """
    p = service.record_tag_scope_revision(
        db, pm_user, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="   ")
    assert p.tag_scope_revision == 1
    row = db.query(ProjectTagScopeRevision).filter_by(revision=1).one()
    assert row.reason == service.INITIAL_SCOPE_REASON

    with pytest.raises(AppError) as e:
        service.record_tag_scope_revision(
            db, pm_user, tag_project.id, new_estimated_tag_count=2000,
            new_status="BASELINED", reason="   ")
    assert e.value.status_code == 422
    db.rollback()
    # The refused revision left nothing behind.
    assert db.get(Project, tag_project.id).tag_scope_revision == 1


def test_scope_cannot_be_set_on_a_non_tag_project(db, make_project, pm_user):
    p = make_project(code="TS-NONE", status=ProjectStatus.active)
    with pytest.raises(AppError) as e:
        service.record_tag_scope_revision(
            db, pm_user, p.id, new_estimated_tag_count=100,
            new_status="PROVISIONAL", reason="r")
    assert e.value.status_code == 422


# ---------- read endpoint ----------
def test_pm_reads_scope_and_history(client, auth_header, db, make_project, make_user):
    pm_h = auth_header("scopepm2@x.com", role=UserRole.project_manager)
    pm = db.query(User).filter(User.email == "scopepm2@x.com").one()
    p = make_project(code="TS-READ", status=ProjectStatus.active)
    p.scope_type = "TAG_BASED"
    db.add(p)
    db.commit()
    service.record_tag_scope_revision(
        db, pm, p.id, new_estimated_tag_count=2500, new_status="BASELINED",
        reason="FMTL scope established")

    res = client.get(f"{BASE}/{p.id}/tag-scope", headers=pm_h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scope_type"] == "TAG_BASED"
    assert body["estimated_tag_count"] == 2500
    assert body["tag_scope_status"] == "BASELINED"
    assert body["tag_scope_revision"] == 1
    assert len(body["revisions"]) == 1
    assert body["revisions"][0]["reason"] == "FMTL scope established"


def test_unconfigured_tag_project_reads_nulls_and_revision_zero(
    client, auth_header, tag_project
):
    pm = auth_header("scopepm3@x.com", role=UserRole.project_manager)
    body = client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=pm).json()
    assert body["estimated_tag_count"] is None
    assert body["tag_scope_status"] is None
    assert body["tag_scope_revision"] == 0
    assert body["revisions"] == []


def test_assigned_head_may_read_tag_scope(client, head_login, tag_project):
    h = head_login("tshead@x.com", tag_project, employee_code="TSH-1")
    assert client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=h).status_code == 200


def test_head_of_another_project_may_not_read_tag_scope(
    client, head_login, tag_project, make_project, db
):
    other = make_project(code="TS-OTHER", status=ProjectStatus.active)
    other.scope_type = "TAG_BASED"
    db.add(other)
    db.commit()
    h = head_login("tshead2@x.com", tag_project, employee_code="TSH-2")
    assert client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=h).status_code == 200
    assert client.get(f"{BASE}/{other.id}/tag-scope", headers=h).status_code == 403


def test_an_employee_outside_the_project_still_gets_nothing(client, auth_header, tag_project):
    """Opening tag scope to "any project viewer" widens nothing for someone who
    is not a viewer: with no membership they cannot read the project, so they
    cannot read its scope either."""
    emp = auth_header("tsemp@x.com", role=UserRole.employee)
    assert client.get(f"{BASE}/{tag_project.id}", headers=emp).status_code == 403
    assert client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=emp).status_code == 403


def test_project_member_may_read_tag_scope_but_not_change_it(
    client, db, make_user, make_employee, make_project_member, tag_project
):
    """Reading is open to any project viewer; only the write is restricted.

    A contributor needs to see how many tags the project covers and why that
    number moved. What they must not do is move it.
    """
    user = make_user("tsmember@x.com", "password123", UserRole.employee)
    emp = make_employee(employee_code="TSM-1", user_id=user.id)
    make_project_member(project_id=tag_project.id, employee_id=emp.id)
    res = client.post(
        "/api/v1/auth/login", json={"identifier": "tsmember@x.com", "password": "password123"}
    )
    h = {"Authorization": f"Bearer {res.json()['access_token']}"}

    assert client.get(f"{BASE}/{tag_project.id}", headers=h).status_code == 200
    assert client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=h).status_code == 200
    assert client.put(
        f"{BASE}/{tag_project.id}/tag-scope",
        json={"estimated_tag_count": 500, "status": "PROVISIONAL", "expected_revision": 0},
        headers=h,
    ).status_code == 403


def test_tag_scope_of_unknown_project_is_404(client, auth_header):
    pm = auth_header("scopepm4@x.com", role=UserRole.project_manager)
    assert client.get(f"{BASE}/{uuid.uuid4()}/tag-scope", headers=pm).status_code == 404


# ---------- project detail read model ----------
def test_project_detail_exposes_scope_fields(client, auth_header, make_project):
    pm = auth_header("scopepm5@x.com", role=UserRole.project_manager)
    p = make_project(code="TS-DETAIL", status=ProjectStatus.active)
    body = client.get(f"{BASE}/{p.id}", headers=pm).json()
    assert body["scope_type"] == "NONE"
    assert body["estimated_tag_count"] is None
    assert body["tag_scope_status"] is None
    assert body["tag_scope_revision"] == 0


def test_project_detail_shows_configured_scope(client, auth_header, db, tag_project):
    pm_h = auth_header("scopepm6@x.com", role=UserRole.project_manager)
    pm = db.query(User).filter(User.email == "scopepm6@x.com").one()
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=2500,
        new_status="BASELINED", reason="r")
    # Two more revisions so the exposed revision number is not trivially 1.
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=2600, new_status="BASELINED", reason="r")
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=2500, new_status="BASELINED", reason="r")

    body = client.get(f"{BASE}/{tag_project.id}", headers=pm_h).json()
    assert body["scope_type"] == "TAG_BASED"
    assert body["estimated_tag_count"] == 2500
    assert body["tag_scope_status"] == "BASELINED"
    assert body["tag_scope_revision"] == 3


# ---------- reclassification guard ----------
def test_tag_based_to_none_allowed_while_no_scope_exists(client, auth_header, tag_project):
    pm = auth_header("scopepm7@x.com", role=UserRole.project_manager)
    res = client.patch(f"{BASE}/{tag_project.id}", headers=pm, json={"scope_type": "NONE"})
    assert res.status_code == 200, res.text
    assert res.json()["scope_type"] == "NONE"


def test_tag_based_to_none_rejected_once_scope_history_exists(
    client, auth_header, db, tag_project
):
    pm_h = auth_header("scopepm8@x.com", role=UserRole.project_manager)
    pm = db.query(User).filter(User.email == "scopepm8@x.com").one()
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="Initial project estimate")

    res = client.patch(f"{BASE}/{tag_project.id}", headers=pm_h, json={"scope_type": "NONE"})
    assert res.status_code == 422
    assert "tag-scope history" in res.json()["error"]["message"]

    # History and current scope survive the rejected attempt.
    db.expire_all()
    p = db.get(Project, tag_project.id)
    assert p.scope_type == "TAG_BASED"
    assert p.estimated_tag_count == 1000
    assert db.query(ProjectTagScopeRevision).count() == 1


def test_other_edits_still_work_on_a_scoped_project(client, auth_header, db, tag_project):
    """The guard must only block the reclassification, not ordinary edits."""
    pm_h = auth_header("scopepm9@x.com", role=UserRole.project_manager)
    pm = db.query(User).filter(User.email == "scopepm9@x.com").one()
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="r")
    res = client.patch(f"{BASE}/{tag_project.id}", headers=pm_h, json={"client": "Still Editable"})
    assert res.status_code == 200, res.text


# ---------- archive / delete behaviour ----------
def test_archiving_a_project_keeps_its_scope_history(client, auth_header, db, tag_project):
    """Archive is a soft delete, so history must survive rather than orphan."""
    pm_h = auth_header("scopepm10@x.com", role=UserRole.project_manager)
    pm = db.query(User).filter(User.email == "scopepm10@x.com").one()
    service.record_tag_scope_revision(
        db, pm, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="r")

    assert client.delete(f"{BASE}/{tag_project.id}", headers=pm_h).status_code == 204
    assert db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).count() == 1


def test_hard_deleting_a_project_cascades_its_history(db, tag_project, pm_user):
    """No orphan rows if a project row is ever removed for real."""
    service.record_tag_scope_revision(
        db, pm_user, tag_project.id, new_estimated_tag_count=1000,
        new_status="PROVISIONAL", reason="r")
    db.execute(text("DELETE FROM projects WHERE id = :i"), {"i": tag_project.id})
    db.commit()
    assert db.query(ProjectTagScopeRevision).count() == 0


# ---------- phase boundary ----------
def test_tag_scope_reads_no_report_data(client, auth_header, tag_project):
    """Phase 3 answers only 'how many tags are expected'. No progress, worked,
    remaining or completion figure is exposed anywhere in the payload."""
    pm = auth_header("scopepm11@x.com", role=UserRole.project_manager)
    body = client.get(f"{BASE}/{tag_project.id}/tag-scope", headers=pm).json()
    for banned in ("progress", "worked", "remaining", "completed", "actual", "percent"):
        assert not any(banned in k for k in body), banned
