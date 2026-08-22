"""API tests for the leave module: CRUD, workflow, and RBAC.

These cover who may do what. Since Phase 10 an approval also draws down the
employee's leave balance and is refused when there isn't enough, so the approval
tests below call `_fund` first - they are asserting authorization, and an
unfunded employee would fail them for an unrelated reason. The balance rule
itself is covered in `test_leave_phase10.py`.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.modules.leave.models import LeaveStatus, LeaveType
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import EmployeeLeaveAdjustment
from app.modules.users.models import UserRole


def _fund(db, employee_id, days: str = "30.00"):
    """Give an employee enough balance for an approval to be about RBAC.

    Posted as an opening adjustment in the CURRENT month - the same shape
    migration 0069 gave every existing employee. The ledger carries it forward,
    so it also covers the leave dates below, which sit a week out and may fall in
    the following month.
    """
    db.add(
        EmployeeLeaveAdjustment(
            employee_id=employee_id,
            effective_month=ledger.month_start(date.today()),
            days=Decimal(days),
            reason="Opening balance",
        )
    )
    db.commit()


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


def test_project_manager_sees_all_leave_requests(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
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
    # project_manager sees ALL leave requests
    assert res["total"] == 3


def test_admin_sees_all(client, make_user, make_employee, make_leave_request, login):
    make_user("adm@x.com", role=UserRole.project_manager)
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
    """Approved leave stays under the project manager's control — cancelling it
    is a domain conflict, not something the employee can drive."""
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=5),
                              end_date=date.today() + timedelta(days=7),
                              status=LeaveStatus.approved)
    h = login("e@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/cancel", headers=h)
    assert res.status_code == 409


# ---------- approve / reject ----------

def test_manager_approves_team_request(client, make_user, make_employee, make_leave_request, login, db):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    _fund(db, emp.id)
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
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
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


def test_project_manager_can_approve_any_leave(client, make_user, make_employee, make_leave_request, login, db):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    other_emp = make_employee(employee_code="EMP")  # no manager_id set
    _ = eu
    _fund(db, other_emp.id)
    req = make_leave_request(employee_id=other_emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("mgr@x.com")
    # project_manager can approve ANY leave request (global access)
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 200


def test_employee_cannot_approve(client, make_user, make_employee, make_leave_request, login):
    u = make_user("e@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=u.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5))
    h = login("e@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403


def test_double_approve_422(client, make_user, make_employee, make_leave_request, login):
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    me = make_employee(employee_code="MGR", user_id=mu.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP", user_id=eu.id, manager_id=me.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=3),
                              end_date=date.today() + timedelta(days=5),
                              status=LeaveStatus.approved)
    h = login("mgr@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 422


def test_admin_can_approve_any(client, make_user, make_employee, make_leave_request, login, db):
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E1", user_id=eu.id)
    _fund(db, emp.id)
    req = make_leave_request(employee_id=emp.id, start_date=date.today() + timedelta(days=1),
                              end_date=date.today() + timedelta(days=2))
    make_user("adm@x.com", role=UserRole.project_manager)
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


# ---------- routing to project head ----------

def test_create_routes_to_project_head_and_notifies(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    hu = make_user("head1@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HEAD1", user_id=hu.id)
    project = make_project(code="RP-1", head_employee_id=head.id)

    eu = make_user("emp10@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E10", user_id=eu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    # `prev_day` must not be in the future - work_reports.service rejects a
    # report dated after today - so it's pinned to the most recent working day
    # at-or-before today, and `leave_date` is the next working day after that
    # (rather than today+7 as originally sketched, which put `prev_day` days
    # in the future on every day of the week and made the report creation
    # below always fail with "Report date cannot be in the future").
    prev_day = date.today()
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    leave_date = prev_day + timedelta(days=1)
    while leave_date.weekday() >= 5:
        leave_date += timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp10@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    note = db.query(Notification).filter(Notification.user_id == hu.id).one()
    assert note.type == "leave_submitted"
    assert note.target_url == f"/attendance?tab=leave&queue=pending&id={body['id']}"


def test_create_no_head_falls_back_to_manager_notification(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    """The previous day's project DOES resolve, but has no Head assigned -
    routed_project_id is still recorded, only the notification falls back."""
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    project = make_project(code="RP-2")  # no head_employee_id

    mu = make_user("mgr10@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR10", user_id=mu.id)
    eu = make_user("emp11@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E11", user_id=eu.id, manager_id=mgr.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    # `prev_day` must not be in the future - work_reports.service rejects a
    # report dated after today - so it's pinned to the most recent working day
    # at-or-before today, and `leave_date` is the next working day after that
    # (rather than today+7 as originally sketched, which put `prev_day` days
    # in the future on every day of the week and made the report creation
    # below always fail with "Report date cannot be in the future").
    prev_day = date.today()
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    leave_date = prev_day + timedelta(days=1)
    while leave_date.weekday() >= 5:
        leave_date += timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp11@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["routed_project_id"] == str(project.id)

    note = db.query(Notification).filter(Notification.user_id == mu.id).one()
    assert note.type == "leave_submitted"
    assert note.target_url == f"/attendance?tab=leave&id={body['id']}"


def test_create_self_as_head_falls_back_to_manager_notification(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    """The employee IS the routed project's Head - notifying them about their
    own submission makes no sense, so this must fall back to their manager,
    same as the no-head case."""
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    mu = make_user("mgr11@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR11", user_id=mu.id)
    eu = make_user("emp12@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E12", user_id=eu.id, manager_id=mgr.id)
    project = make_project(code="RP-3", head_employee_id=emp.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    # `prev_day` must not be in the future - work_reports.service rejects a
    # report dated after today - so it's pinned to the most recent working day
    # at-or-before today, and `leave_date` is the next working day after that
    # (rather than today+7 as originally sketched, which put `prev_day` days
    # in the future on every day of the week and made the report creation
    # below always fail with "Report date cannot be in the future").
    prev_day = date.today()
    while prev_day.weekday() >= 5:
        prev_day -= timedelta(days=1)
    leave_date = prev_day + timedelta(days=1)
    while leave_date.weekday() >= 5:
        leave_date += timedelta(days=1)
    wr_svc.create_work_report(
        db, eu, WorkReportCreate(
            report_date=prev_day,
            tasks=[WorkReportTaskIn(project_id=project.id, description="work", minutes_spent=120)],
        ),
    )

    h = login("emp12@x.com")
    res = client.post(
        "/api/v1/leave-requests", headers=h,
        json=_payload(start_date=str(leave_date), end_date=str(leave_date)),
    )
    assert res.status_code == 201, res.text

    assert db.query(Notification).filter(Notification.user_id == mu.id).count() == 1
    assert db.query(Notification).filter(Notification.user_id == eu.id).count() == 0
