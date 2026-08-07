"""Project tag scope (Phase 4) — the managed establish/revise workflow.

Covers PUT /projects/{id}/tag-scope: the revision lifecycle (0 -> 1 -> 2 -> 3),
count/status/reason validation, the no-op rule, optimistic concurrency, and the
PM / assigned-Head / everyone-else authorization matrix.

Phase 3's schema, read endpoint and TAG_BASED -> NONE guard live in
test_project_tag_scope.py; only the reclassification guard is re-asserted here
(via the write endpoint) because Phase 4 is the first thing that can create the
history it protects.

Nothing in this phase reads Daily Reports, benchmarks or Activity Master, and
nothing computes progress — see test_write_response_exposes_no_progress_fields.
"""
import uuid

import pytest

from app.modules.projects import service
from app.modules.projects.models import Project, ProjectStatus, ProjectTagScopeRevision
from app.modules.users.models import User, UserRole

BASE = "/api/v1/projects"


def scope_url(project_id) -> str:
    return f"{BASE}/{project_id}/tag-scope"


@pytest.fixture()
def tag_project(db, make_project):
    """A TAG_BASED project with no scope established yet (revision 0)."""
    p = make_project(code="TSW-BASE", status=ProjectStatus.active)
    p.scope_type = "TAG_BASED"
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@pytest.fixture()
def pm(client, auth_header):
    """A project manager's auth header."""
    return auth_header("tswpm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def head_login(db, client, make_user, make_employee):
    """Log in an employee assigned as the Head of `project`."""

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


def put_scope(client, headers, project_id, count, status, reason=None, expected=0):
    return client.put(
        scope_url(project_id),
        headers=headers,
        json={
            "estimated_tag_count": count,
            "status": status,
            "reason": reason,
            "expected_revision": expected,
        },
    )


# ---------- initial scope ----------
def test_initial_scope_moves_revision_zero_to_one(client, pm, db, tag_project):
    res = put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL",
                    reason="Initial project estimate")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["estimated_tag_count"] == 1000
    assert body["tag_scope_status"] == "PROVISIONAL"
    assert body["tag_scope_revision"] == 1
    assert body["tag_scope_updated_at"] is not None
    assert len(body["revisions"]) == 1

    rev = body["revisions"][0]
    assert rev["revision"] == 1
    assert rev["previous_estimated_tag_count"] is None
    assert rev["previous_status"] is None
    assert rev["new_estimated_tag_count"] == 1000
    assert rev["new_status"] == "PROVISIONAL"


def test_initial_scope_can_be_baselined_straight_away(client, pm, tag_project):
    body = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                     reason="FMTL scope established").json()
    assert (body["estimated_tag_count"], body["tag_scope_status"]) == (2000, "BASELINED")
    assert body["tag_scope_revision"] == 1


def test_initial_scope_without_a_reason_gets_the_documented_default(
    client, pm, tag_project
):
    """Section 12: the first-ever estimate may default its reason rather than
    forcing the author to restate that the project is being set up."""
    body = put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason=None).json()
    assert body["revisions"][0]["reason"] == service.INITIAL_SCOPE_REASON


def test_project_row_and_history_row_are_written_together(client, pm, db, tag_project):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r")
    db.expire_all()
    p = db.get(Project, tag_project.id)
    rows = db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).all()
    assert len(rows) == 1
    assert (p.estimated_tag_count, p.tag_scope_revision) == (
        rows[0].new_estimated_tag_count, rows[0].revision,
    )


# ---------- revision lifecycle ----------
def test_full_revision_workflow_1000_2000_2500(client, pm, tag_project):
    """The worked example from the spec, through the HTTP API end to end."""
    r1 = put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL",
                   reason="Initial project estimate", expected=0)
    assert r1.json()["tag_scope_revision"] == 1

    r2 = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                   reason="FMTL scope established", expected=1)
    assert r2.json()["tag_scope_revision"] == 2

    r3 = put_scope(client, pm, tag_project.id, 2500, "BASELINED",
                   reason="Additional tags identified from new reference documents",
                   expected=2)
    body = r3.json()
    assert body["tag_scope_revision"] == 3
    assert body["estimated_tag_count"] == 2500
    assert body["tag_scope_status"] == "BASELINED"

    revs = sorted(body["revisions"], key=lambda r: r["revision"])
    assert [r["revision"] for r in revs] == [1, 2, 3]
    assert [r["previous_estimated_tag_count"] for r in revs] == [None, 1000, 2000]
    assert [r["new_estimated_tag_count"] for r in revs] == [1000, 2000, 2500]
    assert [r["previous_status"] for r in revs] == [None, "PROVISIONAL", "BASELINED"]
    assert [r["new_status"] for r in revs] == ["PROVISIONAL", "BASELINED", "BASELINED"]
    assert revs[2]["reason"] == "Additional tags identified from new reference documents"


def test_increasing_scope_preserves_the_superseded_values(client, pm, tag_project):
    """Section 15: growing the estimate must not overwrite what came before."""
    put_scope(client, pm, tag_project.id, 2000, "BASELINED", reason="r", expected=0)
    body = put_scope(client, pm, tag_project.id, 2500, "BASELINED",
                     reason="Additional tags identified from new document",
                     expected=1).json()
    assert body["estimated_tag_count"] == 2500
    assert body["tag_scope_revision"] == 2
    superseded = next(r for r in body["revisions"] if r["revision"] == 1)
    assert superseded["new_estimated_tag_count"] == 2000


def test_reducing_scope_is_allowed_in_this_phase_with_a_reason(client, pm, tag_project):
    """Section 16: no progress service exists yet to validate against, so a
    positive reduction is permitted and recorded."""
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=0)
    res = put_scope(client, pm, tag_project.id, 2200, "BASELINED",
                    reason="Tag register consolidated; duplicates removed", expected=1)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["estimated_tag_count"] == 2200
    assert body["tag_scope_revision"] == 2
    rev2 = next(r for r in body["revisions"] if r["revision"] == 2)
    assert (rev2["previous_estimated_tag_count"], rev2["new_estimated_tag_count"]) == (
        2500, 2200,
    )


def test_provisional_becomes_baselined(client, pm, tag_project):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    body = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                     reason="FMTL scope established", expected=1).json()
    assert body["tag_scope_status"] == "BASELINED"
    rev2 = next(r for r in body["revisions"] if r["revision"] == 2)
    assert (rev2["previous_status"], rev2["new_status"]) == ("PROVISIONAL", "BASELINED")


def test_a_baseline_can_be_revised_again(client, pm, tag_project):
    """Section 17: BASELINED is not a terminal state — the count may still move."""
    put_scope(client, pm, tag_project.id, 2000, "BASELINED", reason="r", expected=0)
    body = put_scope(client, pm, tag_project.id, 2500, "BASELINED",
                     reason="Vendor issued revised tag register", expected=1).json()
    assert (body["estimated_tag_count"], body["tag_scope_status"]) == (2500, "BASELINED")
    assert body["tag_scope_revision"] == 2


def test_status_only_change_is_a_real_revision(client, pm, tag_project):
    """Same count, different status: still a decision worth recording."""
    put_scope(client, pm, tag_project.id, 2000, "PROVISIONAL", reason="r", expected=0)
    body = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                     reason="Scope discovery complete", expected=1).json()
    assert body["tag_scope_revision"] == 2
    assert body["tag_scope_status"] == "BASELINED"


def test_every_historical_row_survives_later_revisions(client, pm, db, tag_project):
    for i, (count, expected) in enumerate([(1000, 0), (2000, 1), (2500, 2), (2200, 3)]):
        put_scope(client, pm, tag_project.id, count, "BASELINED",
                  reason=f"change {i}", expected=expected)
    rows = db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).order_by(ProjectTagScopeRevision.revision).all()
    assert [r.new_estimated_tag_count for r in rows] == [1000, 2000, 2500, 2200]
    assert [r.revision for r in rows] == [1, 2, 3, 4]


# ---------- validation ----------
@pytest.mark.parametrize("bad", [0, -10, -1])
def test_non_positive_counts_are_rejected(client, pm, db, tag_project, bad):
    res = put_scope(client, pm, tag_project.id, bad, "PROVISIONAL", reason="r")
    assert res.status_code == 422, res.text
    db.expire_all()
    assert db.get(Project, tag_project.id).estimated_tag_count is None


@pytest.mark.parametrize("bad", [2.5, "abc", None, ""])
def test_non_integer_counts_are_rejected(client, pm, tag_project, bad):
    res = client.put(
        scope_url(tag_project.id), headers=pm,
        json={"estimated_tag_count": bad, "status": "PROVISIONAL",
              "reason": "r", "expected_revision": 0},
    )
    assert res.status_code == 422, res.text


def test_missing_count_is_rejected(client, pm, tag_project):
    res = client.put(
        scope_url(tag_project.id), headers=pm,
        json={"status": "PROVISIONAL", "reason": "r", "expected_revision": 0},
    )
    assert res.status_code == 422


@pytest.mark.parametrize("count", [1, 1000, 2500])
def test_valid_counts_are_accepted(client, pm, db, make_project, count):
    p = make_project(code=f"TSW-OK-{count}", status=ProjectStatus.active)
    p.scope_type = "TAG_BASED"
    db.add(p)
    db.commit()
    res = put_scope(client, pm, p.id, count, "PROVISIONAL", reason="r")
    assert res.status_code == 200, res.text
    assert res.json()["estimated_tag_count"] == count


def test_unknown_status_is_rejected(client, pm, tag_project):
    """FINALIZED is deliberately not part of the vocabulary."""
    for bad in ("FINALIZED", "NOT_STARTED", "provisional"):
        res = put_scope(client, pm, tag_project.id, 1000, bad, reason="r")
        assert res.status_code == 422, bad


@pytest.mark.parametrize("blank", [None, "", "   ", "\t\n "])
def test_revising_an_existing_scope_requires_a_real_reason(
    client, pm, db, tag_project, blank
):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    res = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                    reason=blank, expected=1)
    assert res.status_code == 422, res.text
    db.expire_all()
    # The rejected attempt changed nothing.
    p = db.get(Project, tag_project.id)
    assert (p.estimated_tag_count, p.tag_scope_revision) == (1000, 1)


def test_reason_is_stored_trimmed(client, pm, tag_project):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    body = put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                     reason="  Vendor issued revised tag register  ", expected=1).json()
    rev2 = next(r for r in body["revisions"] if r["revision"] == 2)
    assert rev2["reason"] == "Vendor issued revised tag register"


def test_scope_cannot_be_set_on_a_non_tag_project(client, pm, make_project):
    p = make_project(code="TSW-NONE", status=ProjectStatus.active)
    res = put_scope(client, pm, p.id, 1000, "PROVISIONAL", reason="r")
    assert res.status_code == 422
    assert "tag-based" in res.json()["error"]["message"]


def test_unknown_project_is_404(client, pm):
    assert put_scope(client, pm, uuid.uuid4(), 1000, "PROVISIONAL", reason="r").status_code == 404


# ---------- no-op ----------
def test_identical_values_do_not_create_a_revision(client, pm, db, tag_project):
    """Section 14: pressing Save without changing anything is not a decision."""
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=0)
    res = put_scope(client, pm, tag_project.id, 2500, "BASELINED",
                    reason="pressed save again", expected=1)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tag_scope_revision"] == 1        # still 1, not 2
    assert len(body["revisions"]) == 1
    assert db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).count() == 1


def test_a_no_op_does_not_touch_the_audit_stamp(client, pm, db, tag_project):
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=0)
    db.expire_all()
    before = db.get(Project, tag_project.id).tag_scope_updated_at
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="again", expected=1)
    db.expire_all()
    assert db.get(Project, tag_project.id).tag_scope_updated_at == before


# ---------- concurrency ----------
def test_stale_expected_revision_is_refused(client, pm, db, tag_project, head_login):
    """Section 22: PM revises 2,500 -> 2,700; the Head's form still says 1."""
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=0)
    put_scope(client, pm, tag_project.id, 2700, "BASELINED", reason="PM revision",
              expected=1)

    stale = put_scope(client, pm, tag_project.id, 2600, "BASELINED",
                      reason="Head revision from a stale form", expected=1)
    assert stale.status_code == 409, stale.text
    assert "changed while you were editing" in stale.json()["error"]["message"]

    db.expire_all()
    p = db.get(Project, tag_project.id)
    assert p.estimated_tag_count == 2700      # the PM's value stands
    assert p.tag_scope_revision == 2
    assert db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).count() == 2                            # no third row from the stale write


def test_expected_revision_from_the_future_is_also_refused(client, pm, tag_project):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    assert put_scope(client, pm, tag_project.id, 2000, "BASELINED",
                     reason="r", expected=7).status_code == 409


def test_initial_set_against_a_stale_zero_is_refused(client, pm, tag_project):
    """Two people both see 'no scope yet'; only the first may establish it."""
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    assert put_scope(client, pm, tag_project.id, 1500, "PROVISIONAL",
                     reason="r", expected=0).status_code == 409


def test_a_refused_write_leaves_history_consistent(client, pm, db, tag_project):
    put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    put_scope(client, pm, tag_project.id, 9999, "BASELINED", reason="r", expected=0)
    db.expire_all()
    p = db.get(Project, tag_project.id)
    rows = db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).all()
    assert len(rows) == 1
    assert p.tag_scope_revision == rows[0].revision == 1
    assert p.estimated_tag_count == rows[0].new_estimated_tag_count == 1000


def test_revision_numbers_stay_dense_and_unique(client, pm, db, tag_project):
    for i, expected in enumerate(range(0, 4)):
        put_scope(client, pm, tag_project.id, 1000 + i * 100, "BASELINED",
                  reason=f"r{i}", expected=expected)
    revisions = [
        r.revision for r in db.query(ProjectTagScopeRevision).filter(
            ProjectTagScopeRevision.project_id == tag_project.id
        ).order_by(ProjectTagScopeRevision.revision).all()
    ]
    assert revisions == [1, 2, 3, 4]
    assert len(set(revisions)) == len(revisions)


# ---------- authorization ----------
def test_pm_may_set_scope_on_any_project(client, pm, db, make_project):
    """A PM heads none of these projects and still administers every one."""
    for code in ("TSW-ANY-1", "TSW-ANY-2"):
        p = make_project(code=code, status=ProjectStatus.active)
        p.scope_type = "TAG_BASED"
        db.add(p)
        db.commit()
        assert put_scope(client, pm, p.id, 1000, "PROVISIONAL",
                         reason="r").status_code == 200


def test_assigned_head_may_set_scope_on_their_project(client, head_login, tag_project):
    h = head_login("tswhead@x.com", tag_project, employee_code="TSWH-1")
    res = put_scope(client, h, tag_project.id, 1500, "PROVISIONAL",
                    reason="Head establishing initial scope")
    assert res.status_code == 200, res.text
    assert res.json()["estimated_tag_count"] == 1500


def test_assigned_head_may_revise_their_project(client, head_login, tag_project):
    h = head_login("tswhead2@x.com", tag_project, employee_code="TSWH-2")
    put_scope(client, h, tag_project.id, 1000, "PROVISIONAL", reason="r", expected=0)
    res = put_scope(client, h, tag_project.id, 2000, "BASELINED",
                    reason="FMTL scope established", expected=1)
    assert res.status_code == 200, res.text
    assert res.json()["tag_scope_revision"] == 2


def test_head_of_another_project_is_forbidden(
    client, head_login, db, tag_project, make_project
):
    other = make_project(code="TSW-OTHER", status=ProjectStatus.active)
    other.scope_type = "TAG_BASED"
    db.add(other)
    db.commit()
    h = head_login("tswhead3@x.com", tag_project, employee_code="TSWH-3")

    assert put_scope(client, h, tag_project.id, 1000, "PROVISIONAL",
                     reason="r").status_code == 200
    assert put_scope(client, h, other.id, 1000, "PROVISIONAL",
                     reason="r").status_code == 403
    db.expire_all()
    assert db.get(Project, other.id).estimated_tag_count is None


def test_plain_employee_is_forbidden(client, auth_header, db, tag_project):
    emp = auth_header("tswemp@x.com", role=UserRole.employee)
    assert put_scope(client, emp, tag_project.id, 1000, "PROVISIONAL",
                     reason="r").status_code == 403
    db.expire_all()
    assert db.get(Project, tag_project.id).estimated_tag_count is None


def test_project_member_may_read_the_project_but_not_write_scope(
    client, db, make_user, make_employee, make_project_member, tag_project
):
    """Membership is a visibility role, never an administrative one."""
    user = make_user("tswmember@x.com", "password123", UserRole.employee)
    emp = make_employee(employee_code="TSWM-1", user_id=user.id)
    make_project_member(project_id=tag_project.id, employee_id=emp.id)
    res = client.post(
        "/api/v1/auth/login",
        json={"identifier": "tswmember@x.com", "password": "password123"},
    )
    h = {"Authorization": f"Bearer {res.json()['access_token']}"}

    assert client.get(f"{BASE}/{tag_project.id}", headers=h).status_code == 200
    assert put_scope(client, h, tag_project.id, 1000, "PROVISIONAL",
                     reason="r").status_code == 403


def test_anonymous_request_is_rejected(client, tag_project):
    res = client.put(
        scope_url(tag_project.id),
        json={"estimated_tag_count": 1000, "status": "PROVISIONAL",
              "reason": "r", "expected_revision": 0},
    )
    assert res.status_code in (401, 403)


# ---------- audit identity ----------
def test_changed_by_comes_from_the_token_not_the_request(
    client, auth_header, db, tag_project
):
    pm_h = auth_header("tswaudit@x.com", role=UserRole.project_manager)
    actor = db.query(User).filter(User.email == "tswaudit@x.com").one()
    other = uuid.uuid4()

    res = client.put(
        scope_url(tag_project.id), headers=pm_h,
        json={
            "estimated_tag_count": 1000, "status": "PROVISIONAL",
            "reason": "r", "expected_revision": 0,
            # Spoof attempts — ignored: unknown fields are not bound, and the
            # server never reads an author or a revision number off the wire.
            "changed_by": str(other),
            "tag_scope_updated_by": str(other),
            "revision": 99,
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tag_scope_revision"] == 1                 # not 99
    assert body["tag_scope_updated_by"] == str(actor.id)   # not `other`
    assert body["revisions"][0]["changed_by"] == str(actor.id)

    db.expire_all()
    row = db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).one()
    assert row.changed_by == actor.id
    assert db.get(Project, tag_project.id).tag_scope_updated_by == actor.id


def test_response_names_the_author(client, auth_header, db, tag_project):
    pm_h = auth_header("tswname@x.com", role=UserRole.project_manager)
    body = put_scope(client, pm_h, tag_project.id, 1000, "PROVISIONAL",
                     reason="r").json()
    assert body["tag_scope_updated_by_name"]
    assert body["revisions"][0]["changed_by_name"]


# ---------- reclassification guard (Phase 3 rule, now reachable) ----------
def test_tag_based_to_none_is_refused_once_a_revision_exists(
    client, pm, db, tag_project
):
    """Section 24: scope history must never be silently discarded."""
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=0)
    put_scope(client, pm, tag_project.id, 2600, "BASELINED", reason="r", expected=1)
    put_scope(client, pm, tag_project.id, 2500, "BASELINED", reason="r", expected=2)

    res = client.patch(f"{BASE}/{tag_project.id}", headers=pm, json={"scope_type": "NONE"})
    assert res.status_code == 422, res.text

    db.expire_all()
    p = db.get(Project, tag_project.id)
    assert p.scope_type == "TAG_BASED"
    assert (p.estimated_tag_count, p.tag_scope_revision) == (2500, 3)
    assert db.query(ProjectTagScopeRevision).filter(
        ProjectTagScopeRevision.project_id == tag_project.id
    ).count() == 3


# ---------- phase boundary ----------
def test_write_response_exposes_no_progress_fields(client, pm, tag_project):
    """Phase 4 configures scope and nothing else: no worked, remaining or
    percentage figure appears anywhere in the payload."""
    body = put_scope(client, pm, tag_project.id, 1000, "PROVISIONAL", reason="r").json()
    keys = set(body) | set(body["revisions"][0])
    for banned in ("progress", "worked", "remaining", "completed", "actual", "percent"):
        assert not any(banned in k for k in keys), banned
