"""Tests for the audit logging module (Phase 4).

Covers the record_audit service, the Tier A/B integration hooks (auth, user
role/password, account linkage, employee lifecycle, project membership), the
read-only RBAC-gated API, filtering/pagination, and immutability.
"""
import uuid

from app.core.database import SessionLocal
from app.modules.audit.constants import AuditAction, EntityType, STATUS_FAILURE
from app.modules.audit.models import AuditLog
from app.modules.audit.service import list_audit_logs, record_audit
from app.modules.users.models import UserRole


# ── helpers ─────────────────────────────────────────────────────────────────

def _logs(action: str | None = None):
    with SessionLocal() as db:
        rows, total = list_audit_logs(db, action=action, limit=100, offset=0)
        return rows, total


def _admin_header(make_user, login):
    make_user("pm@audit.com", role=UserRole.project_manager)
    return login("pm@audit.com")


# ── record_audit service ────────────────────────────────────────────────────

def test_record_audit_snapshots_actor(db, make_user):
    u = make_user("snap@x.com", role=UserRole.project_manager)
    entry = record_audit(
        db, action="test.action", actor=u, entity_type=EntityType.USER,
        entity_id=u.id, commit=True,
    )
    assert entry.id is not None
    assert entry.actor_user_id == u.id
    assert entry.actor_email == "snap@x.com"
    assert entry.actor_role == "project_manager"
    assert entry.status == "success"
    assert entry.details == {}


def test_record_audit_email_override_without_user(db):
    entry = record_audit(
        db, action=AuditAction.LOGIN_FAILURE, actor=None,
        actor_email="ghost@x.com", status=STATUS_FAILURE,
        details={"attempted_email": "ghost@x.com"}, commit=True,
    )
    assert entry.actor_user_id is None
    assert entry.actor_email == "ghost@x.com"
    assert entry.status == "failure"


# ── auth integration ────────────────────────────────────────────────────────

def test_login_success_audited(client, make_user, login):
    make_user("ok@x.com")
    login("ok@x.com")
    rows, total = _logs(action=AuditAction.LOGIN_SUCCESS)
    assert total == 1
    assert rows[0].actor_email == "ok@x.com"


def test_login_failure_audited_and_persisted(client, make_user):
    make_user("bad@x.com")
    res = client.post("/api/v1/auth/login", json={"email": "bad@x.com", "password": "wrong"})
    assert res.status_code == 401
    # The failure event must survive even though the request errored out.
    rows, total = _logs(action=AuditAction.LOGIN_FAILURE)
    assert total == 1
    assert rows[0].status == "failure"
    assert rows[0].details["attempted_email"] == "bad@x.com"


def test_login_unknown_email_audited_without_actor(client):
    res = client.post("/api/v1/auth/login", json={"email": "nobody@x.com", "password": "x"})
    assert res.status_code == 401
    rows, total = _logs(action=AuditAction.LOGIN_FAILURE)
    assert total == 1
    assert rows[0].actor_user_id is None
    assert rows[0].actor_email == "nobody@x.com"


def test_logout_audited(client, make_user, login):
    make_user("out@x.com")
    h = login("out@x.com")
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    _, total = _logs(action=AuditAction.LOGOUT)
    assert total == 1


def test_self_password_change_audited(client, make_user, login):
    make_user("pw@x.com", password="password123")
    h = login("pw@x.com")
    res = client.post("/api/v1/auth/change-password", headers=h,
                      json={"current_password": "password123", "new_password": "newpass456"})
    assert res.status_code == 204
    _, total = _logs(action=AuditAction.PASSWORD_CHANGE_SELF)
    assert total == 1


# ── user admin integration ──────────────────────────────────────────────────

def test_user_create_audited(client, make_user, login):
    h = _admin_header(make_user, login)
    res = client.post("/api/v1/users", headers=h,
                      json={"email": "new@x.com", "password": "password123", "role": "employee"})
    assert res.status_code == 201
    rows, total = _logs(action=AuditAction.USER_CREATE)
    assert total == 1
    assert rows[0].details["email"] == "new@x.com"


def test_user_role_change_audited(client, make_user, login):
    h = _admin_header(make_user, login)
    target = make_user("target@x.com", role=UserRole.employee)
    res = client.patch(f"/api/v1/users/{target.id}/role", headers=h, json={"role": "project_manager"})
    assert res.status_code == 200
    rows, total = _logs(action=AuditAction.USER_ROLE_CHANGE)
    assert total == 1
    assert rows[0].details == {"from": "employee", "to": "project_manager"}


def test_user_status_change_audited(client, make_user, login):
    h = _admin_header(make_user, login)
    target = make_user("deact@x.com", role=UserRole.employee)
    res = client.patch(f"/api/v1/users/{target.id}", headers=h, json={"is_active": False})
    assert res.status_code == 200
    rows, total = _logs(action=AuditAction.USER_STATUS_CHANGE)
    assert total == 1
    assert rows[0].details == {"from": True, "to": False}


def test_admin_password_reset_audited(client, make_user, login):
    h = _admin_header(make_user, login)
    target = make_user("reset@x.com", role=UserRole.employee)
    res = client.patch(f"/api/v1/users/{target.id}/password", headers=h,
                       json={"new_password": "brandnew123"})
    assert res.status_code == 204
    rows, total = _logs(action=AuditAction.USER_PASSWORD_RESET)
    assert total == 1
    assert rows[0].entity_id == target.id


# ── employee account linkage integration ────────────────────────────────────

def test_account_link_and_unlink_audited(client, make_user, make_employee, login):
    h = _admin_header(make_user, login)
    emp = make_employee(employee_code="EMP-AUD")
    create = client.post(f"/api/v1/employees/{emp.id}/account", headers=h,
                         json={"email": "linked@x.com", "password": "password123", "role": "employee"})
    assert create.status_code == 201
    _, linked = _logs(action=AuditAction.EMPLOYEE_ACCOUNT_LINK)
    assert linked == 1

    res = client.delete(f"/api/v1/employees/{emp.id}/account/link", headers=h)
    assert res.status_code == 204
    _, unlinked = _logs(action=AuditAction.EMPLOYEE_ACCOUNT_UNLINK)
    assert unlinked == 1


def test_employee_create_audited(client, make_user, login):
    h = _admin_header(make_user, login)
    res = client.post("/api/v1/employees", headers=h,
                      json={"employee_code": "EMP-NEW", "first_name": "A", "last_name": "B"})
    assert res.status_code == 201
    _, total = _logs(action=AuditAction.EMPLOYEE_CREATE)
    assert total == 1


# ── project membership integration ──────────────────────────────────────────

def test_project_member_add_remove_audited(client, make_user, make_employee, make_project, login):
    from app.modules.projects.models import ProjectStatus
    h = _admin_header(make_user, login)
    emp = make_employee(employee_code="EMP-PM")
    proj = make_project(code="AUD-1", status=ProjectStatus.active)

    res = client.post(f"/api/v1/projects/{proj.id}/members", headers=h,
                      json={"employee_id": str(emp.id), "role": "contributor"})
    assert res.status_code == 201
    _, added = _logs(action=AuditAction.PROJECT_MEMBER_ADD)
    assert added == 1

    res = client.delete(f"/api/v1/projects/{proj.id}/members/{emp.id}", headers=h)
    assert res.status_code in (200, 204)
    _, removed = _logs(action=AuditAction.PROJECT_MEMBER_REMOVE)
    assert removed == 1


# ── API: RBAC, filtering, immutability ──────────────────────────────────────

def test_audit_api_requires_project_manager(client, make_user, login):
    make_user("emp@audit.com", role=UserRole.employee)
    h = login("emp@audit.com")
    assert client.get("/api/v1/audit-logs", headers=h).status_code == 403


def test_audit_api_unauthenticated_blocked(client):
    assert client.get("/api/v1/audit-logs").status_code == 401


def test_audit_api_lists_and_filters(client, make_user, login):
    h = _admin_header(make_user, login)  # login emits LOGIN_SUCCESS
    make_user("x1@x.com")
    client.post("/api/v1/users", headers=h,
                json={"email": "x2@x.com", "password": "password123", "role": "employee"})

    res = client.get("/api/v1/audit-logs", headers=h)
    assert res.status_code == 200
    body = res.json()
    assert body["total"] >= 2
    assert {"items", "total", "limit", "offset"} <= body.keys()

    filtered = client.get(
        f"/api/v1/audit-logs?action={AuditAction.USER_CREATE}", headers=h
    ).json()
    assert filtered["total"] == 1
    assert filtered["items"][0]["action"] == AuditAction.USER_CREATE


def test_audit_api_pagination(client, make_user, login):
    h = _admin_header(make_user, login)
    for i in range(5):
        client.post("/api/v1/users", headers=h,
                    json={"email": f"p{i}@x.com", "password": "password123", "role": "employee"})
    page = client.get("/api/v1/audit-logs?limit=2&offset=0", headers=h).json()
    assert page["limit"] == 2
    assert len(page["items"]) == 2
    assert page["total"] >= 5


def test_audit_log_is_append_only():
    # No update/delete route is exposed for audit logs.
    from app.main import app
    paths = {(r.path, m) for r in app.routes for m in getattr(r, "methods", set())}
    assert not any(
        p.startswith("/api/v1/audit-logs") and method in {"PUT", "PATCH", "DELETE"}
        for p, method in paths
    )


def test_get_single_audit_log(client, make_user, login):
    h = _admin_header(make_user, login)
    with SessionLocal() as db:
        entry = record_audit(db, action="test.single", commit=True)
        entry_id = entry.id
    res = client.get(f"/api/v1/audit-logs/{entry_id}", headers=h)
    assert res.status_code == 200
    assert res.json()["action"] == "test.single"


def test_get_missing_audit_log_404(client, make_user, login):
    h = _admin_header(make_user, login)
    res = client.get(f"/api/v1/audit-logs/{uuid.uuid4()}", headers=h)
    assert res.status_code == 404
