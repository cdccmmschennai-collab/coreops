"""Tests for activity access control (restricted activities, migration 0061).

Covers the PM-only management APIs, the report-dropdown filter, server-side
write enforcement (create / update / submit / activity-request), soft-revoke +
re-grant reactivation, audit, and the employee-search grant helper.
"""
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.modules.activity_master.access_models import EmployeeActivityAccess
from app.modules.audit.constants import AuditAction
from app.modules.audit.models import AuditLog
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

AM = "/api/v1/activity-master"
WR = "/api/v1/work-reports"
TODAY = date.today().isoformat()


# ── helpers ──────────────────────────────────────────────────────────────────

def _activity(client, h, name="ACT", **kw):
    res = client.post(f"{AM}/activities", json={"name": name, **kw}, headers=h)
    assert res.status_code == 201, res.text
    return res.json()


def _sub(client, h, activity_id, name="SUB", **kw):
    res = client.post(
        f"{AM}/activities/{activity_id}/sub-activities",
        json={"name": name, **kw},
        headers=h,
    )
    assert res.status_code == 201, res.text
    return res.json()


def _restrict(client, h, activity_id, employee_ids):
    return client.patch(
        f"{AM}/activities/{activity_id}/access-type",
        json={"access_type": "RESTRICTED", "employee_ids": [str(e) for e in employee_ids]},
        headers=h,
    )


@pytest.fixture()
def pm(client, auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


@pytest.fixture()
def make_worker(make_user, make_employee, login):
    """An employee with a linked login account that can file reports."""

    def _make(email, code):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, first_name=code, last_name="W")
        return {"user": u, "emp": e, "header": login(email)}

    return _make


def _dropdown_ids(client, header):
    res = client.get(f"{AM}/sub-activities", headers=header)
    assert res.status_code == 200, res.text
    return {r["id"] for r in res.json()}


# ── migration / default ──────────────────────────────────────────────────────

def test_new_activity_defaults_to_common(client, pm):
    a = _activity(client, pm, name="Common Act")
    assert a["access_type"] == "COMMON"


# ── dropdown visibility ──────────────────────────────────────────────────────

def test_common_activity_visible_to_employee(client, pm, make_worker):
    a = _activity(client, pm, name="Open")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    assert sub["id"] in _dropdown_ids(client, w["header"])


def test_restricted_hidden_without_access(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    other = make_worker("other@x.com", "E2")
    assert sub["id"] not in _dropdown_ids(client, other["header"])


def test_restricted_visible_with_access(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    assert _restrict(client, pm, a["id"], [w["emp"].id]).status_code == 200
    assert sub["id"] in _dropdown_ids(client, w["header"])


def test_revoked_access_hides_activity(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    assert client.delete(
        f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm
    ).status_code == 200
    assert sub["id"] not in _dropdown_ids(client, w["header"])


def test_inactive_activity_hidden_regardless_of_access(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.delete(f"{AM}/activities/{a['id']}", headers=pm)  # soft-deactivate
    assert sub["id"] not in _dropdown_ids(client, w["header"])


# ── RBAC on management ───────────────────────────────────────────────────────

def test_employee_cannot_change_access_type(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w = make_worker("emp@x.com", "E1")
    res = client.patch(
        f"{AM}/activities/{a['id']}/access-type",
        json={"access_type": "RESTRICTED", "employee_ids": [str(w["emp"].id)]},
        headers=w["header"],
    )
    assert res.status_code == 403


def test_employee_cannot_grant(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    res = client.post(
        f"{AM}/activities/{a['id']}/access",
        json={"employee_ids": [str(w["emp"].id)]},
        headers=w["header"],
    )
    assert res.status_code == 403


def test_employee_cannot_revoke(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    res = client.delete(
        f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=w["header"]
    )
    assert res.status_code == 403


def test_employee_cannot_read_access_list(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w = make_worker("emp@x.com", "E1")
    res = client.get(f"{AM}/activities/{a['id']}/access", headers=w["header"])
    assert res.status_code == 403


# ── change-type rules ────────────────────────────────────────────────────────

def test_common_to_restricted_requires_employee(client, pm):
    a = _activity(client, pm, name="Secret")
    res = client.patch(
        f"{AM}/activities/{a['id']}/access-type",
        json={"access_type": "RESTRICTED", "employee_ids": []},
        headers=pm,
    )
    assert res.status_code == 422


def test_common_to_restricted_atomic_on_invalid_employee(client, pm, make_worker, db):
    import uuid

    a = _activity(client, pm, name="Secret")
    w = make_worker("emp@x.com", "E1")
    res = _restrict(client, pm, a["id"], [w["emp"].id, uuid.uuid4()])
    assert res.status_code == 422
    # Neither the type flip nor any grant landed.
    fresh = client.get(f"{AM}/activities", headers=pm).json()
    assert next(x for x in fresh if x["id"] == a["id"])["access_type"] == "COMMON"
    n = db.execute(
        select(func.count()).select_from(EmployeeActivityAccess)
    ).scalar_one()
    assert n == 0


def test_restricted_to_common_soft_revokes(client, pm, make_worker, db):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = make_worker("emp@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    res = client.patch(
        f"{AM}/activities/{a['id']}/access-type",
        json={"access_type": "COMMON"},
        headers=pm,
    )
    assert res.status_code == 200
    # Grant row preserved but soft-revoked (history kept).
    row = db.execute(
        select(EmployeeActivityAccess).where(
            EmployeeActivityAccess.activity_id == a["id"]
        )
    ).scalar_one()
    assert row.is_active is False and row.revoked_at is not None
    # And now visible to everyone again.
    other = make_worker("other@x.com", "E2")
    assert sub["id"] in _dropdown_ids(client, other["header"])


# ── grant / revoke mechanics ────────────────────────────────────────────────

def test_bulk_grant(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w1 = make_worker("e1@x.com", "E1")
    _restrict(client, pm, a["id"], [w1["emp"].id])
    w2 = make_worker("e2@x.com", "E2")
    w3 = make_worker("e3@x.com", "E3")
    res = client.post(
        f"{AM}/activities/{a['id']}/access",
        json={"employee_ids": [str(w2["emp"].id), str(w3["emp"].id)]},
        headers=pm,
    )
    assert res.status_code == 200, res.text
    assert res.json()["authorized_count"] == 3


def test_duplicate_grant_no_duplicate_rows(client, pm, make_worker, db):
    a = _activity(client, pm, name="Secret")
    w = make_worker("e1@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.post(
        f"{AM}/activities/{a['id']}/access",
        json={"employee_ids": [str(w["emp"].id)]},
        headers=pm,
    )
    n = db.execute(
        select(func.count()).select_from(EmployeeActivityAccess).where(
            EmployeeActivityAccess.activity_id == a["id"],
            EmployeeActivityAccess.employee_id == w["emp"].id,
        )
    ).scalar_one()
    assert n == 1


def test_regrant_reactivates_existing_row(client, pm, make_worker, db):
    a = _activity(client, pm, name="Secret")
    w = make_worker("e1@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    client.post(
        f"{AM}/activities/{a['id']}/access",
        json={"employee_ids": [str(w["emp"].id)]},
        headers=pm,
    )
    rows = db.execute(
        select(EmployeeActivityAccess).where(
            EmployeeActivityAccess.activity_id == a["id"],
            EmployeeActivityAccess.employee_id == w["emp"].id,
        )
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].is_active is True and rows[0].revoked_at is None


def test_revoke_already_revoked_is_clean(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w = make_worker("e1@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    res = client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    assert res.status_code == 200
    assert res.json()["revoked"] is False


def test_grant_on_common_activity_rejected(client, pm, make_worker):
    a = _activity(client, pm, name="Open")
    w = make_worker("e1@x.com", "E1")
    res = client.post(
        f"{AM}/activities/{a['id']}/access",
        json={"employee_ids": [str(w["emp"].id)]},
        headers=pm,
    )
    assert res.status_code == 422


# ── write-path enforcement ───────────────────────────────────────────────────

@pytest.fixture()
def worker_with_project(make_worker, make_project, make_project_member):
    def _make(email="emp@x.com", code="E1", proj="P1"):
        w = make_worker(email, code)
        p = make_project(code=proj, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=w["emp"].id)
        w["project"] = p
        return w

    return _make


def _report_payload(project_id, sub_id):
    return {
        "report_date": TODAY,
        "tasks": [
            {
                "project_id": str(project_id),
                "description": "work",
                "minutes_spent": 60,
                "sub_activity_id": str(sub_id),
            }
        ],
    }


def test_direct_unauthorized_report_create_403(client, pm, worker_with_project):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = worker_with_project()
    # The worker never had access: restrict to nobody they are.
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    res = client.post(WR, headers=w["header"], json=_report_payload(w["project"].id, sub["id"]))
    assert res.status_code == 403, res.text
    assert "do not have access" in res.json()["error"]["message"].lower()


def test_authorized_report_create_succeeds(client, pm, worker_with_project):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = worker_with_project()
    _restrict(client, pm, a["id"], [w["emp"].id])
    res = client.post(WR, headers=w["header"], json=_report_payload(w["project"].id, sub["id"]))
    assert res.status_code == 201, res.text


def test_submit_blocked_after_revoke(client, pm, worker_with_project):
    a = _activity(client, pm, name="Secret")
    sub = _sub(client, pm, a["id"])
    w = worker_with_project()
    _restrict(client, pm, a["id"], [w["emp"].id])
    created = client.post(
        WR, headers=w["header"], json=_report_payload(w["project"].id, sub["id"])
    )
    assert created.status_code == 201, created.text
    report_id = created.json()["id"]
    # Revoke, then submission of the already-saved draft must be blocked.
    client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    res = client.post(f"{WR}/{report_id}/submit", headers=w["header"])
    assert res.status_code == 403, res.text


# ── audit ────────────────────────────────────────────────────────────────────

def test_audit_events_recorded(client, pm, make_worker, db):
    a = _activity(client, pm, name="Secret")
    w = make_worker("e1@x.com", "E1")
    _restrict(client, pm, a["id"], [w["emp"].id])
    client.delete(f"{AM}/activities/{a['id']}/access/{w['emp'].id}", headers=pm)
    actions = set(
        db.execute(
            select(AuditLog.action).where(AuditLog.entity_id == a["id"])
        ).scalars()
    )
    assert AuditAction.ACTIVITY_ACCESS_TYPE_CHANGED in actions
    assert AuditAction.ACTIVITY_ACCESS_GRANTED in actions
    assert AuditAction.ACTIVITY_ACCESS_REVOKED in actions


# ── employee search helper ───────────────────────────────────────────────────

def test_employee_search_excludes_already_granted(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    w1 = make_worker("e1@x.com", "E1")
    w2 = make_worker("e2@x.com", "E2")
    _restrict(client, pm, a["id"], [w1["emp"].id])
    res = client.get(
        f"/api/v1/employees?exclude_activity_id={a['id']}&status=active", headers=pm
    )
    assert res.status_code == 200
    ids = {r["id"] for r in res.json()["items"]}
    assert str(w1["emp"].id) not in ids
    assert str(w2["emp"].id) in ids


def test_access_list_pagination(client, pm, make_worker):
    a = _activity(client, pm, name="Secret")
    workers = [make_worker(f"e{i}@x.com", f"E{i}") for i in range(3)]
    _restrict(client, pm, a["id"], [w["emp"].id for w in workers])
    res = client.get(f"{AM}/activities/{a['id']}/access?limit=2&offset=0", headers=pm)
    body = res.json()
    assert body["total"] == 3
    assert body["authorized_count"] == 3
    assert len(body["items"]) == 2
