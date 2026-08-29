"""API tests for the leave module: CRUD, workflow, and RBAC.

These cover who may do what. Since Phase 10 an approval also draws down the
employee's leave balance and is refused when there isn't enough, so the approval
tests below call `_fund` first - they are asserting authorization, and an
unfunded employee would fail them for an unrelated reason. The balance rule
itself is covered in `test_leave_phase10.py`.
"""
from datetime import date, timedelta
from decimal import Decimal

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.working_days import next_working_day, previous_working_day
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import EmployeeLeaveAdjustment
from app.modules.users.models import UserRole


def _report_and_leave_dates(db) -> tuple[date, date]:
    """`(prev_day, leave_date)` - two CONSECUTIVE working days for the routing
    tests, where `prev_day` is never in the future.

    Both come from the shared company calendar rather than a local Mon-Fri rule,
    so the pair stays genuinely consecutive as the office week does (a working
    1st/3rd/5th Saturday is a working day here too). That matters because
    `leave/routing.py` resolves the evidence date as
    `previous_working_day(leave_date)` - which is `prev_day` BY CONSTRUCTION
    here, so the work report filed below is always the one routing looks for.

    `prev_day` is at-or-before today because `work_reports.service` rejects a
    report dated after today.
    """
    prev_day = previous_working_day(db, date.today() + timedelta(days=1))
    return prev_day, next_working_day(db, prev_day)


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


def _make_leave(db, employee_id, *, routed_project_id=None, start=None, end=None):
    req = LeaveRequest(
        employee_id=employee_id,
        leave_type=LeaveType.casual,
        start_date=start or (date.today() + timedelta(days=7)),
        end_date=end or (date.today() + timedelta(days=7)),
        reason="Test",
        status=LeaveStatus.pending,
        routed_project_id=routed_project_id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


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

    prev_day, leave_date = _report_and_leave_dates(db)
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


def test_create_no_head_falls_back_to_pm_notification(
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
    make_employee(employee_code="MGR10", user_id=mu.id)
    eu = make_user("emp11@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E11", user_id=eu.id, reporting_pm_id=mu.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    prev_day, leave_date = _report_and_leave_dates(db)
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


def test_a_project_heads_own_leave_is_unrouted_and_goes_to_the_pm(
    client, db, make_user, make_employee, make_project, make_project_member, login,
):
    """The requester is a Project Head. Their leave must not be routed to ANY
    Project Head - not themselves and not a colleague - so routed_project_id
    stays NULL and the PM, the authoritative approver for a Head, is notified."""
    from datetime import timedelta

    from app.modules.notifications.models import Notification
    from app.modules.work_reports import service as wr_svc
    from app.modules.work_reports.schemas import WorkReportCreate, WorkReportTaskIn

    mu = make_user("mgr11@x.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR11", user_id=mu.id)
    eu = make_user("emp12@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="E12", user_id=eu.id, reporting_pm_id=mu.id)
    project = make_project(code="RP-3", head_employee_id=emp.id)
    make_project_member(project_id=project.id, employee_id=emp.id)

    prev_day, leave_date = _report_and_leave_dates(db)
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
    assert res.json()["routed_project_id"] is None

    assert db.query(Notification).filter(Notification.user_id == mu.id).count() == 1
    assert db.query(Notification).filter(Notification.user_id == eu.id).count() == 0


def test_another_head_cannot_approve_a_project_heads_own_leave(
    client, db, make_user, make_employee, make_project, login,
):
    """A Head's own leave is unrouted, and an unrouted request has no Head
    reviewer at all - so a DIFFERENT Project Head is refused just like any other
    employee, leaving the PM as the only approver."""
    a_u = make_user("head-own-a@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HOA", user_id=a_u.id)
    make_project(code="OWN-A", head_employee_id=head_a.id)

    b_u = make_user("head-own-b@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HOB", user_id=b_u.id)
    make_project(code="OWN-B", head_employee_id=head_b.id)

    _fund(db, head_a.id)
    req = _make_leave(db, head_a.id, routed_project_id=None)

    # Head B - a Project Head, but not of anything this request is routed to.
    res_b = client.post(
        f"/api/v1/leave-requests/{req.id}/approve", headers=login("head-own-b@x.com"), json={}
    )
    assert res_b.status_code == 403, res_b.text

    # Head A - the requester - cannot approve their own either.
    res_a = client.post(
        f"/api/v1/leave-requests/{req.id}/approve", headers=login("head-own-a@x.com"), json={}
    )
    assert res_a.status_code == 403, res_a.text


def test_the_pm_can_approve_a_project_heads_own_leave(
    client, db, make_user, make_employee, make_project, login,
):
    """The other half of the rule: the PM really is the authoritative approver
    for an unrouted request, so the Head's leave is not left undecidable."""
    make_user("pm-own@x.com", role=UserRole.project_manager)
    a_u = make_user("head-own-c@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HOC", user_id=a_u.id)
    make_project(code="OWN-C", head_employee_id=head.id)

    _fund(db, head.id)
    req = _make_leave(db, head.id, routed_project_id=None)

    res = client.post(
        f"/api/v1/leave-requests/{req.id}/approve", headers=login("pm-own@x.com"), json={}
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_the_pm_is_notified_of_a_cancellation_request_on_an_unrouted_leave(
    client, db, make_user, make_employee, login,
):
    """The PM fallback carries every event the recipient chain handles, not just
    submission - a cancellation request on an unrouted leave has to reach the
    person who will decide it, deep-linked to the queue that contains it."""
    from app.modules.notifications.models import Notification

    mu = make_user("pm-cancel@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PMC", user_id=mu.id)
    eu = make_user("emp-cancel@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="ECX", user_id=eu.id, reporting_pm_id=mu.id)

    req = _make_leave(db, emp.id, routed_project_id=None)
    req.status = LeaveStatus.approved
    db.add(req)
    db.commit()

    res = client.post(
        f"/api/v1/leave-requests/{req.id}/request-cancellation",
        headers=login("emp-cancel@x.com"),
    )
    assert res.status_code == 200, res.text

    note = (
        db.query(Notification)
        .filter(Notification.user_id == mu.id,
                Notification.type == "leave_cancellation_requested")
        .one()
    )
    assert note.target_url == f"/attendance?tab=leave&queue=cancellation&id={req.id}"


def test_an_employee_with_no_reporting_pm_notifies_nobody_without_failing(
    client, db, make_user, make_employee, login,
):
    """No routed project and no reporting PM on record. That is a legitimate
    data state, not an error: the request is still created and nothing raises."""
    from app.modules.notifications.models import Notification

    eu = make_user("emp-orphan@x.com", role=UserRole.employee)
    make_employee(
        employee_code="EORPH", user_id=eu.id, manager_id=None, reporting_pm_id=None
    )

    before = db.query(Notification).count()
    res = client.post(
        "/api/v1/leave-requests", headers=login("emp-orphan@x.com"), json=_payload()
    )

    assert res.status_code == 201, res.text
    assert res.json()["routed_project_id"] is None
    assert db.query(Notification).count() == before


def test_the_line_manager_is_never_notified_of_a_leave_request(
    client, db, make_user, make_employee, login,
):
    """`manager_id` is no longer a rung of the chain. A line manager cannot
    approve leave, so notifying them told somebody who could not act while the
    PM who could was never told."""
    from app.modules.notifications.models import Notification

    lm_u = make_user("linemgr@x.com", role=UserRole.employee)
    line_mgr = make_employee(employee_code="LM1", user_id=lm_u.id)
    mu = make_user("pm-lm@x.com", role=UserRole.project_manager)
    make_employee(employee_code="PMLM", user_id=mu.id)
    eu = make_user("emp-lm@x.com", role=UserRole.employee)
    make_employee(
        employee_code="ELM", user_id=eu.id, manager_id=line_mgr.id, reporting_pm_id=mu.id
    )

    res = client.post(
        "/api/v1/leave-requests", headers=login("emp-lm@x.com"), json=_payload()
    )
    assert res.status_code == 201, res.text

    assert db.query(Notification).filter(Notification.user_id == lm_u.id).count() == 0
    assert db.query(Notification).filter(Notification.user_id == mu.id).count() == 1


def _fund_and_login(login, email):
    return login(email)


def test_head_sees_only_own_routed_requests(
    client, db, make_user, make_employee, make_project, login,
):
    head_a_u = make_user("heada@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HA", user_id=head_a_u.id)
    head_b_u = make_user("headb@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HB", user_id=head_b_u.id)
    project_a = make_project(code="SC-A", head_employee_id=head_a.id)
    project_b = make_project(code="SC-B", head_employee_id=head_b.id)

    emp_a_u = make_user("empa@x.com", role=UserRole.employee)
    emp_a = make_employee(employee_code="EA", user_id=emp_a_u.id)
    emp_b_u = make_user("empb@x.com", role=UserRole.employee)
    emp_b = make_employee(employee_code="EB", user_id=emp_b_u.id)
    make_employee(employee_code="EC", user_id=make_user("empc@x.com").id)  # unrelated, no routing

    req_a = _make_leave(db, emp_a.id, routed_project_id=project_a.id)
    req_b = _make_leave(db, emp_b.id, routed_project_id=project_b.id)

    h = login("heada@x.com")
    res = client.get("/api/v1/leave-requests", headers=h, params={"status": "pending"}).json()
    ids = {row["id"] for row in res["items"]}
    assert str(req_a.id) in ids
    assert str(req_b.id) not in ids


def test_head_can_approve_own_routed_request(
    client, db, make_user, make_employee, make_project, login,
):
    head_u = make_user("headc@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HC", user_id=head_u.id)
    project = make_project(code="SC-C", head_employee_id=head.id)

    emp_u = make_user("empd@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="ED", user_id=emp_u.id)
    _fund(db, emp.id)

    req = _make_leave(db, emp.id, routed_project_id=project.id)

    h = login("headc@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"


def test_head_cannot_approve_other_heads_request(
    client, db, make_user, make_employee, make_project, login,
):
    head_a_u = make_user("heade@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HE", user_id=head_a_u.id)
    make_project(code="SC-D", head_employee_id=head_a.id)
    head_b_u = make_user("headf@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HF", user_id=head_b_u.id)
    project_b = make_project(code="SC-E", head_employee_id=head_b.id)

    emp_u = make_user("empe@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EF", user_id=emp_u.id)
    req = _make_leave(db, emp.id, routed_project_id=project_b.id)

    h = login("heade@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_plain_employee_cannot_approve_anyone(
    client, db, make_user, make_employee, make_project, login,
):
    project = make_project(code="SC-F")  # no head
    emp_u = make_user("empf@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EG", user_id=emp_u.id)
    other_u = make_user("empg@x.com", role=UserRole.employee)
    other = make_employee(employee_code="EH", user_id=other_u.id)
    req = _make_leave(db, other.id, routed_project_id=project.id)

    h = login("empf@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_plain_employee_cannot_approve_unrouted_request(
    client, db, make_user, make_employee, login,
):
    other_u = make_user("otheremp@x.com", role=UserRole.employee)
    other = make_employee(employee_code="OE", user_id=other_u.id)
    req = _make_leave(db, other.id, routed_project_id=None)

    attacker_u = make_user("attacker@x.com", role=UserRole.employee)
    make_employee(employee_code="AT", user_id=attacker_u.id)

    h = login("attacker@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_head_cannot_approve_own_leave_even_if_self_routed(
    client, db, make_user, make_employee, make_project, login,
):
    head_u = make_user("headg@x.com", role=UserRole.employee)
    head = make_employee(employee_code="HG", user_id=head_u.id)
    project = make_project(code="SC-G", head_employee_id=head.id)
    req = _make_leave(db, head.id, routed_project_id=project.id)

    h = login("headg@x.com")
    res = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h, json={})
    assert res.status_code == 403, res.text


def test_reassigned_head_takes_over_review_authority(
    client, db, make_user, make_employee, make_project, login,
):
    """Spec §15: the PROJECT on the leave row is historical and frozen, but
    WHO may review it is always the project's CURRENT head_employee_id - a
    reassignment after the request was filed must be honoured immediately,
    with no change to the leave row itself."""
    head_a_u = make_user("headh@x.com", role=UserRole.employee)
    head_a = make_employee(employee_code="HH", user_id=head_a_u.id)
    head_b_u = make_user("headi@x.com", role=UserRole.employee)
    head_b = make_employee(employee_code="HI", user_id=head_b_u.id)
    project = make_project(code="SC-H", head_employee_id=head_a.id)

    emp_u = make_user("empi@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EI", user_id=emp_u.id)
    _fund(db, emp.id)  # casual leave deducts balance - approval needs it funded
    req = _make_leave(db, emp.id, routed_project_id=project.id)

    # Reassign the project's Head from A to B - simulates the PM's existing
    # `PUT /projects/{id}/head` action; nothing on the leave row changes.
    project.head_employee_id = head_b.id
    db.add(project)
    db.commit()

    h_a = login("headh@x.com")
    res_a = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h_a, json={})
    assert res_a.status_code == 403, res_a.text  # Head A lost authority

    h_b = login("headi@x.com")
    res_b = client.post(f"/api/v1/leave-requests/{req.id}/approve", headers=h_b, json={})
    assert res_b.status_code == 200, res_b.text  # Head B has it now


# ---------- working_days on the response ------------------------------------
#
# The Leave Detail page no longer derives its Duration from `(end - start) + 1`;
# it renders `working_days`, which the backend computes with
# `effects.leave_working_days` - the same calculation an approval charges
# against. The office-week rule itself (1st/3rd/5th Saturday working, 2nd/4th
# not, Sunday not, holiday and working_day overrides) is pinned in
# `test_office_week.py`; these only assert that the API carries the answer.

AUG_FRI = date(2026, 8, 28)   # Friday          - working
AUG_SAT = date(2026, 8, 29)   # 5th Saturday    - working
AUG_SUN = date(2026, 8, 30)   # Sunday          - non-working
AUG_MON = date(2026, 8, 31)   # Monday          - working


def test_detail_reports_three_working_days_for_28_to_31_august(
    client, make_user, make_employee, make_leave_request, login,
):
    """The case this change exists for: a four-day range that costs three days,
    because the 5th Saturday works and the Sunday does not."""
    u = make_user("wd1@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="WD1", user_id=u.id)
    req = make_leave_request(
        employee_id=emp.id, start_date=AUG_FRI, end_date=AUG_MON
    )

    h = login("wd1@x.com")
    res = client.get(f"/api/v1/leave-requests/{req.id}", headers=h)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["working_days"] == 3
    # The requested range is untouched - the count is not the span.
    assert body["start_date"] == "2026-08-28"
    assert body["end_date"] == "2026-08-31"


def test_a_company_holiday_inside_the_range_lowers_the_count(
    client, db, make_user, make_employee, make_leave_request, login,
):
    """Proves the count really comes from the calendar table rather than from a
    hardcoded week: declaring the working Saturday a holiday drops it to 2."""
    u = make_user("wd2@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="WD2", user_id=u.id)
    req = make_leave_request(
        employee_id=emp.id, start_date=AUG_FRI, end_date=AUG_MON
    )
    db.add(
        CalendarEvent(
            event_date=AUG_SAT,
            title="Company holiday",
            event_type=CalendarEventType.holiday,
        )
    )
    db.commit()

    h = login("wd2@x.com")
    res = client.get(f"/api/v1/leave-requests/{req.id}", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["working_days"] == 2


def test_a_working_day_override_raises_the_count(
    client, db, make_user, make_employee, make_leave_request, login,
):
    """The inverse: declaring the Sunday a working day brings it back to 4."""
    u = make_user("wd3@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="WD3", user_id=u.id)
    req = make_leave_request(
        employee_id=emp.id, start_date=AUG_FRI, end_date=AUG_MON
    )
    db.add(
        CalendarEvent(
            event_date=AUG_SUN,
            title="Declared working",
            event_type=CalendarEventType.working_day,
        )
    )
    db.commit()

    h = login("wd3@x.com")
    res = client.get(f"/api/v1/leave-requests/{req.id}", headers=h)
    assert res.status_code == 200, res.text
    assert res.json()["working_days"] == 4


def test_the_list_carries_working_days_too(
    client, make_user, make_employee, make_leave_request, login,
):
    u = make_user("wd4@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="WD4", user_id=u.id)
    make_leave_request(employee_id=emp.id, start_date=AUG_FRI, end_date=AUG_MON)

    h = login("wd4@x.com")
    res = client.get("/api/v1/leave-requests", headers=h)
    assert res.status_code == 200, res.text
    assert [row["working_days"] for row in res.json()["items"]] == [3]
