"""Phase 10 - leave management foundation.

One test per rule Phase 10 introduces, and nothing that another file already
covers. The lifecycle plumbing, RBAC scoping and cancellation state machine are
tested in `test_leave_api.py` and `test_leave_cancellation.py`; what is new here
is that an approval MOVES STATE - it marks calendar days and draws down a
balance - so these pin the movement and its guards.

Dates are pinned to known weekdays rather than derived from `date.today()`, so a
run on a Saturday cannot change how many working days a range contains.

    docker exec wms-backend-1 pytest tests/test_leave_phase10.py
"""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.leave_balances import ledger
from app.modules.leave_balances.models import EmployeeLeaveBalanceHistory
from app.modules.users.models import UserRole

API = "/api/v1/leave-requests"

# A Monday far enough out that nothing collides with "today".
MON = date(2027, 3, 1)
# The ledger month every date in this file falls in. Opening balances are posted
# here and derived balances are read here, so the fixture and the assertions are
# talking about the same month.
MONTH = date(2027, 3, 1)
TUE = MON + timedelta(days=1)
WED = MON + timedelta(days=2)
FRI = MON + timedelta(days=4)
NEXT_MON = MON + timedelta(days=7)


@pytest.fixture()
def team(make_user, make_employee):
    """A project manager, a SECOND project manager (needed to review the first
    one's own leave), and one employee."""
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    m2 = make_user("mgr2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR2", user_id=m2.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP069", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp, "manager_user": mu}


@pytest.fixture()
def fund(team, make_leave_adjustment):
    """Give the employee an opening balance in the month these tests operate in.

    Phase 3: there is no stored balance to write any more. An opening balance is
    an adjustment posted to a month, which is also exactly what migration 0069
    did for every existing employee - so these tests exercise the real shape of
    a funded employee rather than a fixture-only one.
    """

    def _fund(value="10.00", employee_id=None):
        make_leave_adjustment(
            employee_id=employee_id or team["employee"].id,
            effective_month=MONTH,
            days=value,
            reason="Opening balance",
        )

    return _fund


def _balance(db, employee_id) -> Decimal:
    """The DERIVED balance for the month these tests operate in.

    Phase 3 made this a fold over allocations, adjustments and the `leave`
    attendance rows - so an approval shows up here because it MARKED DAYS, not
    because anything wrote a number.
    """
    return ledger.closing_balance(db, employee_id, MONTH)


def _days(db, employee_id):
    """(date, status) for every attendance row this employee has."""
    return [
        (r.attendance_date, r.status)
        for r in db.query(AttendanceRecord)
        .filter_by(employee_id=employee_id)
        .order_by(AttendanceRecord.attendance_date)
        .all()
    ]


def _approve(client, login, req_id, email="mgr@x.com"):
    return client.post(f"{API}/{req_id}/approve", headers=login(email), json={})


# ======================================================================
# Balance movement
# ======================================================================

def test_pending_request_reserves_nothing(client, login, team, fund, db):
    """Section 12A - the balance moves on approval, never on submission."""
    fund("10.00")
    res = client.post(API, headers=login("emp@x.com"), json={
        "leave_type": "casual", "start_date": MON.isoformat(),
        "end_date": TUE.isoformat(), "reason": "Family function",
    })
    assert res.status_code == 201, res.text
    assert res.json()["status"] == "pending"

    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("10.00")
    assert db.query(EmployeeLeaveBalanceHistory).count() == 0
    assert _days(db, team["employee"].id) == []


def test_approval_deducts_balance_and_marks_the_calendar(
    client, login, team, fund, make_leave_request, db
):
    """Sections 12B and 8 together - the core of Phase 10.

    The days become official `leave` records with NO times (so the popover
    renders "-" rather than a shift boundary standing in for a punch), the
    balance drops by the same count, and the mandatory history row is written.
    """
    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    assert _approve(client, login, req.id).status_code == 200

    db.expire_all()
    assert _days(db, team["employee"].id) == [
        (MON, AttendanceStatus.leave),
        (TUE, AttendanceStatus.leave),
        (WED, AttendanceStatus.leave),
    ]
    for row in db.query(AttendanceRecord).all():
        assert (row.check_in_at, row.check_out_at, row.total_minutes) == (None, None, 0)

    assert _balance(db, team["employee"].id) == Decimal("7.00")
    # Phase 3: the deduction IS the three rows above. No balance was written, so
    # the PM-correction history stays empty - an approval is not a manual edit,
    # and it is audited in `audit_logs` instead (see the audit test below, which
    # still asserts the balance movement was recorded).
    assert db.query(EmployeeLeaveBalanceHistory).count() == 0


def test_weekends_are_neither_marked_nor_charged(
    client, login, team, fund, make_leave_request, db
):
    """A Friday-to-Monday leave costs two days, not four."""
    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=FRI, end_date=NEXT_MON
    )
    _approve(client, login, req.id)

    db.expire_all()
    assert [d for d, _ in _days(db, team["employee"].id)] == [FRI, NEXT_MON]
    assert _balance(db, team["employee"].id) == Decimal("8.00")


def test_unpaid_leave_marks_the_calendar_without_touching_balance(
    client, login, team, fund, make_leave_request, db
):
    """Unpaid leave is real absence but is not drawn from the pool - and so is
    not subject to the balance guard either, which is the point of it."""
    fund("1.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED,
        leave_type=LeaveType.unpaid,
    )
    assert _approve(client, login, req.id).status_code == 200

    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("1.00")
    assert len(_days(db, team["employee"].id)) == 3


def test_rejection_moves_nothing(client, login, team, fund, make_leave_request, db):
    """Section 12C."""
    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    res = client.post(f"{API}/{req.id}/reject", headers=login("mgr@x.com"),
                      json={"comment": "Project deadline"})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"

    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("10.00")
    assert _days(db, team["employee"].id) == []
    assert db.query(EmployeeLeaveBalanceHistory).count() == 0


# ======================================================================
# Cancellation reverses the approval
# ======================================================================

def test_cancelling_pending_costs_nothing_and_cancelling_approved_restores(
    client, login, team, fund, make_leave_request, db
):
    """Sections 12D and 12E - both cancellation paths, one round trip each."""
    fund("10.00")
    # 12D: a pending request never moved anything, so cancelling it moves nothing.
    pending = make_leave_request(
        employee_id=team["employee"].id, start_date=NEXT_MON, end_date=NEXT_MON
    )
    assert client.post(f"{API}/{pending.id}/cancel",
                       headers=login("emp@x.com")).status_code == 200
    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("10.00")
    assert _days(db, team["employee"].id) == []

    # 12E: an approved one gives its days and its balance back.
    approved = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    _approve(client, login, approved.id)
    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("7.00")

    client.post(f"{API}/{approved.id}/request-cancellation", headers=login("emp@x.com"))
    assert client.post(f"{API}/{approved.id}/approve-cancellation",
                       headers=login("mgr@x.com")).status_code == 200

    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("10.00")
    assert _days(db, team["employee"].id) == []


def test_cancellation_never_removes_a_day_the_pm_re_decided(
    client, login, team, fund, make_leave_request, db
):
    """The narrow-removal rule, and what deriving the balance fixed underneath it.

    A PM overrules one day of an approved leave: the employee actually worked the
    Tuesday. Cancelling the leave afterwards must not delete that ruling.

    THE BALANCE NOW SELF-CORRECTS, and this is a deliberate Phase 3 change. Under
    the old stored counter the approval subtracted 3, the PM's edit subtracted
    nothing (it did not know about balances), and the cancellation added back only
    the 2 rows it removed - leaving the employee permanently 1 day short, with
    nothing on the calendar to justify the charge. That was exactly the mutable
    drift the ledger removes: consumption is the `leave` rows that exist, so the
    moment Tuesday becomes `present` it stops costing anything, and cancelling the
    rest returns the employee to where they started.
    """
    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    _approve(client, login, req.id)
    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("7.00")

    # The PM decides the employee actually worked the Tuesday.
    tuesday = db.query(AttendanceRecord).filter_by(
        employee_id=team["employee"].id, attendance_date=TUE
    ).one()
    tuesday.status = AttendanceStatus.present
    tuesday.check_in_at = datetime(2027, 3, 2, 9, 0, tzinfo=timezone.utc)
    db.commit()

    # A worked day is not a leave day, so it stops consuming immediately - no
    # cancellation, no correction and no job needed.
    db.expire_all()
    assert _balance(db, team["employee"].id) == Decimal("8.00")

    client.post(f"{API}/{req.id}/request-cancellation", headers=login("emp@x.com"))
    client.post(f"{API}/{req.id}/approve-cancellation", headers=login("mgr@x.com"))

    db.expire_all()
    # The PM's ruling survives: only the two untouched leave rows were removed.
    assert _days(db, team["employee"].id) == [(TUE, AttendanceStatus.present)]
    assert _balance(db, team["employee"].id) == Decimal("10.00")


def test_rejecting_a_cancellation_keeps_the_leave_and_the_deduction(
    client, login, team, fund, make_leave_request, db
):
    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=TUE
    )
    _approve(client, login, req.id)
    client.post(f"{API}/{req.id}/request-cancellation", headers=login("emp@x.com"))
    client.post(f"{API}/{req.id}/reject-cancellation", headers=login("mgr@x.com"))

    db.expire_all()
    assert db.get(LeaveRequest, req.id).status == LeaveStatus.approved
    assert _balance(db, team["employee"].id) == Decimal("8.00")
    assert len(_days(db, team["employee"].id)) == 2


# ======================================================================
# Guards
# ======================================================================

def test_nobody_reviews_their_own_leave_but_another_pm_can(
    client, login, team, fund, make_leave_request, db
):
    """Section 3. The role check alone is not enough - a project manager is an
    employee too, and would otherwise approve their own leave and balance."""
    fund("10.00", employee_id=team["manager"].id)
    own = make_leave_request(
        employee_id=team["manager"].id, start_date=MON, end_date=MON
    )

    blocked = _approve(client, login, own.id)          # the author, a PM
    assert blocked.status_code == 403, blocked.text
    assert "your own leave" in blocked.json()["error"]["message"]
    db.expire_all()
    assert db.get(LeaveRequest, own.id).status == LeaveStatus.pending

    # ...and the same guard covers deciding the cancellation of your own leave.
    assert _approve(client, login, own.id, email="mgr2@x.com").status_code == 200
    client.post(f"{API}/{own.id}/request-cancellation", headers=login("mgr@x.com"))
    for path in ("approve-cancellation", "reject-cancellation"):
        assert client.post(f"{API}/{own.id}/{path}",
                           headers=login("mgr@x.com")).status_code == 403, path

    db.expire_all()
    assert _balance(db, team["manager"].id) == Decimal("9.00")


def test_employee_cannot_approve_or_reject(client, login, team, make_leave_request):
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=MON
    )
    h = login("emp@x.com")
    for path in ("approve", "reject"):
        assert client.post(f"{API}/{req.id}/{path}", headers=h,
                           json={}).status_code == 403, path


def test_overlapping_requests_are_refused_but_dead_ones_do_not_block(
    client, login, team, make_leave_request
):
    """Section 12I - the exact duplicate and every partial overlap with it. A
    rejected or cancelled request is not an absence, so it never blocks."""
    h = login("emp@x.com")
    body = {"leave_type": "casual", "start_date": MON.isoformat(),
            "end_date": WED.isoformat()}
    assert client.post(API, headers=h, json=body).status_code == 201

    assert client.post(API, headers=h, json=body).status_code == 422   # duplicate
    partial = client.post(API, headers=h, json={
        "leave_type": "casual", "start_date": TUE.isoformat(),
        "end_date": FRI.isoformat(),
    })
    assert partial.status_code == 422
    assert "already have a pending leave request" in partial.json()["error"]["message"]

    make_leave_request(
        employee_id=team["employee"].id, start_date=NEXT_MON, end_date=NEXT_MON,
        status=LeaveStatus.rejected,
    )
    assert client.post(API, headers=h, json={
        "leave_type": "casual", "start_date": NEXT_MON.isoformat(),
        "end_date": NEXT_MON.isoformat(),
    }).status_code == 201


def test_approval_blocked_when_balance_is_insufficient(
    client, login, team, fund, make_leave_request, db
):
    """Section 12J - and the request survives intact so it can be refiled."""
    fund("1.50")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    res = _approve(client, login, req.id)
    assert res.status_code == 422, res.text
    assert "Insufficient leave balance" in res.json()["error"]["message"]

    db.expire_all()
    assert db.get(LeaveRequest, req.id).status == LeaveStatus.pending
    assert _balance(db, team["employee"].id) == Decimal("1.50")
    assert _days(db, team["employee"].id) == []


def test_an_existing_official_decision_is_never_overwritten(
    client, login, team, fund, make_leave_request, make_attendance, db
):
    """Section 12H - a day already ruled on keeps its ruling, and is not charged."""
    fund("10.00")
    make_attendance(employee_id=team["employee"].id, attendance_date=TUE,
                    status=AttendanceStatus.comp_off)
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=WED
    )
    assert _approve(client, login, req.id).status_code == 200

    db.expire_all()
    assert _days(db, team["employee"].id) == [
        (MON, AttendanceStatus.leave),
        (TUE, AttendanceStatus.comp_off),
        (WED, AttendanceStatus.leave),
    ]
    # Two days marked, so two charged - the comp-off day is not leave.
    assert _balance(db, team["employee"].id) == Decimal("8.00")


# ======================================================================
# The biometric boundary
# ======================================================================

def test_approved_leave_reads_as_leave_without_demanding_review(
    client, login, team, fund, make_leave_request, db
):
    """Sections 5, 6 and 12F, through the calendar's own read.

    Approved leave + zero punches must produce a settled Leave day, not a
    review. The biometric classification still honestly says `no_record` - the
    device really did see nothing - and no times are invented.
    """
    from app.modules.biometric.service import list_daily_summary

    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=MON
    )
    _approve(client, login, req.id)
    db.expire_all()

    items, _schedule = list_daily_summary(
        db, actor=team["manager_user"], provider="easytime",
        employee_id=team["employee"].id, date_from=MON, date_to=MON,
    )
    day = next(i for i in items if i["summary_date"] == MON)

    assert day["review_required"] is False
    assert day["classification"] == "no_record"   # evidence stays evidence
    assert (day["first_in"], day["last_out"], day["worked_minutes"]) == (None, None, None)


def test_approval_does_not_touch_biometric_punches(
    client, login, team, fund, make_leave_request, db
):
    """Section 12G - device evidence is never rewritten, and an approved leave
    day that HAS punches keeps every one of them for the later conflict phase."""
    from app.modules.biometric.models import BiometricPunch

    punch = BiometricPunch(
        provider="easytime", external_transaction_id="tx-p10-1",
        external_employee_code="69",
        punch_time=datetime(2027, 3, 1, 3, 40, tzinfo=timezone.utc),
        raw_punch_state="0", raw_payload={},
    )
    db.add(punch)
    db.commit()
    before = (punch.punch_time, punch.external_employee_code, punch.employee_id)

    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=MON
    )
    _approve(client, login, req.id)

    db.expire_all()
    after = db.get(BiometricPunch, punch.id)
    assert (after.punch_time, after.external_employee_code, after.employee_id) == before
    assert db.query(BiometricPunch).count() == 1


# ======================================================================
# Audit
# ======================================================================

def test_every_decision_is_audited_through_the_central_log(
    client, login, team, fund, make_leave_request, db
):
    """Section 10 - the existing audit architecture, not a second mechanism.
    The details carry what the request row cannot: the movement itself."""
    from app.modules.audit.models import AuditLog

    fund("10.00")
    req = make_leave_request(
        employee_id=team["employee"].id, start_date=MON, end_date=TUE
    )
    _approve(client, login, req.id)
    client.post(f"{API}/{req.id}/request-cancellation", headers=login("emp@x.com"))
    client.post(f"{API}/{req.id}/approve-cancellation", headers=login("mgr@x.com"))

    db.expire_all()
    rows = db.query(AuditLog).filter(AuditLog.entity_id == req.id).all()
    actions = {r.action for r in rows}
    assert {"leave.request.approve", "leave.cancellation.request",
            "leave.cancellation.approve"} <= actions

    approved = next(r for r in rows if r.action == "leave.request.approve")
    assert approved.details["days_marked"] == 2
    assert approved.details["balance_before"] == "10.00"
    assert approved.details["balance_after"] == "8.00"
