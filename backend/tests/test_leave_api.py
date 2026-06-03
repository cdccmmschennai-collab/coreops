"""API tests for the leave module: CRUD, workflow, and RBAC."""
from datetime import date, timedelta

from app.modules.leave.models import LeaveStatus, LeaveType
from app.modules.users.models import UserRole


def _payload(**overrides):
    base = {
        "leave_type": "casual",
        "start_date": str(date.today() + timedelta(days=7)),
        "end_date": str(date.today() + timedelta(days=9)),
        "reason": "Family trip",
    }
    base.update(overrides)
    return base


# ---------- create ----------

def test_employee_can_create(client, make_user, make_employee, login):
    u = make_user("emp@x.com", role=UserRole.employee)
    make_employee(employee_code="E1", user_id=u.id)
    h = login("emp@x.com")
    res = client.post("/api/v1/leave-requests", headers=h, json=_payload())
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == "pending"
    assert body["leave_type"] == "casual"


def test_create_requires_employee_profile(client, make_user, login):
    make_user("nomp@x.com", role=UserRole.employee)
    h = login("nomp@x.com")
    res = client.post("/api/v1/leave-requests", headers=h, json=_payload())
    assert res.status_code == 422


def test_end_before_start_422(client, make_user, make_employee, login):
    u = make_user("emp@x.com", role=UserRole.employee)
    make_employee(employee_code="E1", user_id=u.id)
    h = login("emp@x.com")
    res = client.post(
        "/api/v1/leave-requests",
        headers=h,
        json=_payload(start_date=str(date.today() + timedelta(days=5)),
                      end_date=str(date.today() + timedelta(days=3))),
    )
    assert res.status_code == 422


# ---------- list / scope ----------

def test_employee_sees_only_own(client, make_user, make_employee, make_leave_request, login):
    u1 = make_user("e1@x.com", role=UserRole.employee)
    e1 = make_employee(employee_code="E1", user_id=u1.id)
    u2 = make_user("e2@x.com", role=UserRole.employee)
    e2 = make_employee(employee_code="E2", user_id=u2.id)
    make_leave_request(employee_id=e1.id, start_date=date.today(), end_date=date.today())
    make_leave_request(employee_id=e2.id, start_date=date.today(), end_date=date.today())
    h = login("e1@x.com")
    res = client.get("/api/v1/leave-requests", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["employee_id"] == str(e1.id)


def test_manager_sees_team_and_self(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    ou = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="OTHER", user_id=ou.id)
    make_leave_request(employee_id=me.id, start_date=date.today(), end_date=date.today())
    make_leave_request(employee_id=emp.id, start_date=date.today(), end_date=date.today())
    make_leave_request(employee_id=other.id, start_date=date.today(), end_date=date.today())
    h = login("mgr@x.com")
    res = client.get("/api/v1/leave-requests", headers=h).json()
    assert res["total"] == 2  # own + team; not other
    emp_ids = {r["employee_id"] for r in res["items"]}
    assert str(other.id) not in emp_ids


def test_admin_sees_all(client, make_user, make_employee, make_leave_request, login):
    make_user("adm@x.com", role=UserRole.admin)
    for i in range(3):
        eu = make_user(f"e{i}@x.com", role=UserRole.employee)
        emp = make_employee(employee_code=f"E{i}", user_id=eu.id)
        make_leave_request(employee_id=emp.id, start_date=date.today(), end_date=date.today())
    h = login("adm@x.com")
    res = client.get("/api/v1/leave-requests", headers=h).json()
    assert res["total"] == 3


# ---------- update (own pending) ----------

def test_employee_can_update_pending(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=5),
                              end_date=date.today() + timedelta(days=7))
    h = login("e@x.com")
    res = client.patch(f"/api/v1/leave-requests/{req.id}", headers=h,
                       json={"reason": "Updated reason", "leave_type": "sick"})
    assert res.status_code == 200
    assert res.json()["reason"] == "Updated reason"
    assert res.json()["leave_type"] == "sick"


def test_cannot_update_approved(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=5),
                              end_date=date.today() + timedelta(days=7),
                              status=LeaveStatus.approved)
    h = login("e@x.com")
    res = client.patch(f"/api/v1/leave-requests/{req.id}", headers=h, json={"reason": "x"})
    assert res.status_code == 403


# ---------- cancel ----------

def test_employee_can_cancel_pending(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=5),
                              end_date=date.today() + timedelta(days=7))
    h = login("e@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/cancel", headers=h)
    assert res.status_code == 200
    assert res.json()["status"] == "cancelled"


def test_cannot_cancel_approved(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=5),
                              end_date=date.today() + timedelta(days=7),
                              status=LeaveStatus.approved)
    h = login("e@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/cancel", headers=h)
    assert res.status_code == 403


# ---------- approve / reject ----------

def test_manager_approves_team_request(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("mgr@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h,
                      json={"comment": "Approved, enjoy!"})
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "approved"
    assert body["manager_comment"] == "Approved, enjoy!"


def test_manager_rejects_team_request(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("mgr@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/reject", headers=h,
                      json={"comment": "Clash with sprint deadline"})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


def test_manager_cannot_approve_non_team(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.manager)
    make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    other_emp = make_employee(employee_code="EMP")  # no manager_id set
    _ = eu
    req = make_leave_request(employee_id=other_emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("mgr@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403


def test_employee_cannot_approve(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("e@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403


def test_double_approve_422(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5),
                              status=LeaveStatus.approved)
    h = login("mgr@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 422


def test_admin_can_approve_any(client, make_user, make_employee, make_leave_request, login):
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=eu.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=1),
                              end_date=date.today() + timedelta(days=2))
    make_user("adm@x.com", role=UserRole.admin)
    h = login("adm@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 200
    assert res.json()["status"] == "approved"


# ---------- filters ----------

def test_filter_by_status(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    make_leave_request(employee_id=emp.id, start_date=date.today(), end_date=date.today(),
                        status=LeaveStatus.pending)
    make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=10),
                        end_date=date.today() + timedelta(days=12),
                        status=LeaveStatus.approved)
    h = login("e@x.com")
    res = client.get("/api/v1/leave-requests?status=pending", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["status"] == "pending"
