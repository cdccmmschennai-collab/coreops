"""Tests for the notifications module: creation, RBAC isolation, read/unread,
integration hooks (leave, reports, project assignment)."""
from datetime import date, timedelta

from app.modules.notifications.models import Notification
from app.modules.notifications.service import create_notification
from app.modules.users.models import UserRole


# ── helpers ────────────────────────────────────────────────────────────────

def _notif(db, user_id, type_="test", title="T", message="M"):
    n = create_notification(db, user_id=user_id, type_=type_, title=title, message=message)
    db.commit()
    return n


# ── creation ───────────────────────────────────────────────────────────────

def test_create_notification(db, make_user):
    u = make_user("a@x.com")
    n = _notif(db, u.id, type_="leave_approved", title="Approved", message="Your leave was approved.")
    assert n.id is not None
    assert n.user_id == u.id
    assert n.type == "leave_approved"
    assert n.is_read is False


def test_notification_default_unread(db, make_user):
    u = make_user("b@x.com")
    n = _notif(db, u.id)
    assert n.is_read is False


# ── list & unread count ─────────────────────────────────────────────────────

def test_list_notifications_own_only(client, make_user, login):
    u1 = make_user("u1@x.com")
    u2 = make_user("u2@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        _notif(db, u1.id, title="For U1")
        _notif(db, u1.id, title="Also U1")
        _notif(db, u2.id, title="For U2")

    h = login("u1@x.com")
    res = client.get("/api/v1/notifications", headers=h)
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert all(n["title"] in ("For U1", "Also U1") for n in data["items"])


def test_unread_count(client, make_user, login):
    u = make_user("uc@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        n1 = _notif(db, u.id)
        n2 = _notif(db, u.id)
        n3 = _notif(db, u.id)

    h = login("uc@x.com")
    res = client.get("/api/v1/notifications/unread-count", headers=h)
    assert res.status_code == 200
    assert res.json()["count"] == 3


def test_list_unread_filter(client, make_user, login):
    u = make_user("uf@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        n1 = _notif(db, u.id, title="Read one")
        n2 = _notif(db, u.id, title="Unread")
        n1.is_read = True
        db.add(n1)
        db.commit()

    h = login("uf@x.com")
    res = client.get("/api/v1/notifications?unread_only=true", headers=h)
    assert res.status_code == 200
    assert res.json()["total"] == 1
    assert res.json()["items"][0]["title"] == "Unread"


# ── mark read ───────────────────────────────────────────────────────────────

def test_mark_single_read(client, make_user, login):
    u = make_user("mr@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        n = _notif(db, u.id)
        notif_id = n.id

    h = login("mr@x.com")
    res = client.post(f"/api/v1/notifications/{notif_id}/read", headers=h)
    assert res.status_code == 200
    assert res.json()["is_read"] is True

    count_res = client.get("/api/v1/notifications/unread-count", headers=h)
    assert count_res.json()["count"] == 0


def test_mark_all_read(client, make_user, login):
    u = make_user("mar@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        for _ in range(5):
            _notif(db, u.id)

    h = login("mar@x.com")
    assert client.get("/api/v1/notifications/unread-count", headers=h).json()["count"] == 5
    res = client.post("/api/v1/notifications/read-all", headers=h)
    assert res.status_code == 200
    assert res.json()["count"] == 0
    assert client.get("/api/v1/notifications/unread-count", headers=h).json()["count"] == 0


def test_mark_read_wrong_user_404(client, make_user, login):
    u1 = make_user("u1r@x.com")
    u2 = make_user("u2r@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        n = _notif(db, u1.id)
        notif_id = n.id

    h2 = login("u2r@x.com")
    res = client.post(f"/api/v1/notifications/{notif_id}/read", headers=h2)
    assert res.status_code == 404


# ── RBAC isolation ──────────────────────────────────────────────────────────

def test_rbac_isolation_employee(client, make_user, login):
    admin = make_user("adm@x.com", role=UserRole.project_manager)
    emp   = make_user("emp@x.com", role=UserRole.employee)
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        _notif(db, admin.id, title="Admin notif")
        _notif(db, emp.id,   title="Emp notif")

    h = login("emp@x.com")
    res = client.get("/api/v1/notifications", headers=h).json()
    assert res["total"] == 1
    assert res["items"][0]["title"] == "Emp notif"


def test_unauthenticated_blocked(client):
    res = client.get("/api/v1/notifications")
    assert res.status_code == 401


# ── leave integration ───────────────────────────────────────────────────────

def _setup_leave_actors(make_user, make_employee):
    mgr_u  = make_user("mgr@lv.com", role=UserRole.project_manager)
    emp_u  = make_user("emp@lv.com", role=UserRole.employee)
    mgr_e  = make_employee(employee_code="MGR-LV", user_id=mgr_u.id)
    emp_e  = make_employee(employee_code="EMP-LV", user_id=emp_u.id, manager_id=mgr_e.id)
    return mgr_u, emp_u, mgr_e, emp_e


def test_leave_submitted_notifies_manager(
    client, make_user, make_employee, login
):
    mgr_u, emp_u, *_ = _setup_leave_actors(make_user, make_employee)
    start = str(date.today() + timedelta(days=7))
    end   = str(date.today() + timedelta(days=9))
    h = login("emp@lv.com")
    res = client.post("/api/v1/leave-requests", headers=h,
                      json={"leave_type": "casual", "start_date": start, "end_date": end})
    assert res.status_code == 201

    h_mgr = login("mgr@lv.com")
    count = client.get("/api/v1/notifications/unread-count", headers=h_mgr).json()["count"]
    assert count == 1
    notifs = client.get("/api/v1/notifications", headers=h_mgr).json()["items"]
    assert notifs[0]["type"] == "leave_submitted"


def test_leave_approved_notifies_employee(
    client, make_user, make_employee, make_leave_request, login
):
    mgr_u, emp_u, mgr_e, emp_e = _setup_leave_actors(make_user, make_employee)
    req = make_leave_request(employee_id=emp_e.id,
                             start_date=date.today() + timedelta(days=3),
                             end_date=date.today() + timedelta(days=5))
    h_mgr = login("mgr@lv.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h_mgr, json={})
    assert res.status_code == 200

    h_emp = login("emp@lv.com")
    notifs = client.get("/api/v1/notifications", headers=h_emp).json()["items"]
    assert any(n["type"] == "leave_approved" for n in notifs)


def test_leave_rejected_notifies_employee(
    client, make_user, make_employee, make_leave_request, login
):
    mgr_u, emp_u, mgr_e, emp_e = _setup_leave_actors(make_user, make_employee)
    req = make_leave_request(employee_id=emp_e.id,
                             start_date=date.today() + timedelta(days=3),
                             end_date=date.today() + timedelta(days=5))
    h_mgr = login("mgr@lv.com")
    client.post(f"/api/v1/leave-requests/{req.id}/reject", headers=h_mgr,
                json={"comment": "Too busy"})

    h_emp = login("emp@lv.com")
    notifs = client.get("/api/v1/notifications", headers=h_emp).json()["items"]
    assert any(n["type"] == "leave_rejected" for n in notifs)


def test_leave_cancelled_notifies_manager(
    client, make_user, make_employee, make_leave_request, login
):
    mgr_u, emp_u, mgr_e, emp_e = _setup_leave_actors(make_user, make_employee)
    req = make_leave_request(employee_id=emp_e.id,
                             start_date=date.today() + timedelta(days=3),
                             end_date=date.today() + timedelta(days=5))
    h_emp = login("emp@lv.com")
    client.post(f"/api/v1/leave-requests/{req.id}/cancel", headers=h_emp)

    h_mgr = login("mgr@lv.com")
    notifs = client.get("/api/v1/notifications", headers=h_mgr).json()["items"]
    assert any(n["type"] == "leave_cancelled" for n in notifs)


# ── report integration ──────────────────────────────────────────────────────

def test_report_approved_notifies_author(
    client, make_user, make_employee, make_project, make_project_member, login
):
    mgr_u = make_user("mgr@rp.com", role=UserRole.project_manager)
    emp_u = make_user("emp@rp.com", role=UserRole.employee)
    mgr_e = make_employee(employee_code="MGR-RP", user_id=mgr_u.id)
    emp_e = make_employee(employee_code="EMP-RP", user_id=emp_u.id, manager_id=mgr_e.id)
    proj  = make_project(code="RPT-1", status=__import__(
        "app.modules.projects.models", fromlist=["ProjectStatus"]
    ).ProjectStatus.active)
    make_project_member(project_id=proj.id, employee_id=emp_e.id)

    h_emp = login("emp@rp.com")
    create_res = client.post("/api/v1/work-reports", headers=h_emp, json={
        "report_date": str(date.today()),
        "tasks": [{"project_id": str(proj.id), "description": "Work done", "minutes_spent": 120}],
    })
    assert create_res.status_code == 201
    report_id = create_res.json()["id"]

    client.post(f"/api/v1/work-reports/{report_id}/submit", headers=h_emp)

    h_mgr = login("mgr@rp.com")
    client.post(f"/api/v1/work-reports/{report_id}/approve", headers=h_mgr)

    notifs = client.get("/api/v1/notifications", headers=h_emp).json()["items"]
    assert any(n["type"] == "report_approved" for n in notifs)


# ── project assignment integration ─────────────────────────────────────────

def test_project_assigned_notifies_employee(
    client, make_user, make_employee, make_project, login
):
    admin_u = make_user("adm@pr.com", role=UserRole.project_manager)
    emp_u   = make_user("emp@pr.com", role=UserRole.employee)
    emp_e   = make_employee(employee_code="EMP-PR", user_id=emp_u.id)
    from app.modules.projects.models import ProjectStatus
    proj    = make_project(code="PROJ-A", status=ProjectStatus.active)

    h_adm = login("adm@pr.com")
    res = client.post(f"/api/v1/projects/{proj.id}/members", headers=h_adm,
                      json={"employee_id": str(emp_e.id), "role": "member"})
    assert res.status_code == 201

    h_emp = login("emp@pr.com")
    notifs = client.get("/api/v1/notifications", headers=h_emp).json()["items"]
    assert any(n["type"] == "project_assigned" for n in notifs)


# ── entity_type & entity_id ────────────────────────────────────────────────

def test_notification_has_entity_fields(db, make_user):
    import uuid
    u = make_user("ef@x.com")
    eid = uuid.uuid4()
    n = create_notification(db, user_id=u.id, type_="leave_approved", title="T",
                            message="M", entity_type="leave_request", entity_id=eid)
    db.commit()
    assert n.entity_type == "leave_request"
    assert n.entity_id == eid


# ── target_url ─────────────────────────────────────────────────────────────

def test_target_url_persisted(db, make_user):
    u = make_user("tu@x.com")
    n = create_notification(db, user_id=u.id, type_="report_approved", title="T",
                            message="M", target_url="/work-reports/abc-123")
    db.commit()
    assert n.target_url == "/work-reports/abc-123"


def test_target_url_none_by_default(db, make_user):
    u = make_user("tun@x.com")
    n = create_notification(db, user_id=u.id, type_="test", title="T", message="M")
    db.commit()
    assert n.target_url is None


def test_target_url_in_api_response(client, make_user, login):
    u = make_user("tur@x.com")
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        create_notification(db, user_id=u.id, type_="project_assigned", title="T",
                            message="M", target_url="/projects/some-id")
        db.commit()
    h = login("tur@x.com")
    items = client.get("/api/v1/notifications", headers=h).json()["items"]
    assert items[0]["target_url"] == "/projects/some-id"


def test_leave_submitted_notification_has_target_url(
    client, make_user, make_employee, login
):
    """Leave-submitted notification sent to manager carries target_url."""
    from datetime import date, timedelta
    mgr_u  = make_user("mgr@tu.com", role=UserRole.project_manager)
    emp_u  = make_user("emp@tu.com", role=UserRole.employee)
    mgr_e  = make_employee(employee_code="MGR-TU", user_id=mgr_u.id)
    emp_e  = make_employee(employee_code="EMP-TU", user_id=emp_u.id, manager_id=mgr_e.id)

    start = str(date.today() + timedelta(days=7))
    end   = str(date.today() + timedelta(days=9))
    h = login("emp@tu.com")
    res = client.post("/api/v1/leave-requests", headers=h,
                      json={"leave_type": "casual", "start_date": start, "end_date": end})
    assert res.status_code == 201
    leave_id = res.json()["id"]

    h_mgr = login("mgr@tu.com")
    notifs = client.get("/api/v1/notifications", headers=h_mgr).json()["items"]
    assert len(notifs) == 1
    assert notifs[0]["target_url"] == f"/attendance?tab=leave&id={leave_id}"


def test_project_assigned_notification_has_target_url(
    client, make_user, make_employee, make_project, login
):
    """Project-assigned notification carries /projects/{id} as target_url."""
    from app.modules.projects.models import ProjectStatus
    pm_u  = make_user("pm@tu.com", role=UserRole.project_manager)
    emp_u = make_user("emp@tu.com", role=UserRole.employee)
    emp_e = make_employee(employee_code="EMP-PR2", user_id=emp_u.id)
    proj  = make_project(code="PROJ-TU", status=ProjectStatus.active)

    h = login("pm@tu.com")
    client.post(f"/api/v1/projects/{proj.id}/members", headers=h,
                json={"employee_id": str(emp_e.id), "role": "contributor"})

    h_emp = login("emp@tu.com")
    notifs = client.get("/api/v1/notifications", headers=h_emp).json()["items"]
    assert any(
        n["type"] == "project_assigned" and n["target_url"] == f"/projects/{proj.id}"
        for n in notifs
    )
