"""Phase 11 - the Permission foundation.

One test per rule Phase 11 actually introduces, and nothing else. The monthly
allowance is DERIVED (4h minus that month's approved hours), so what these pin is
that the derivation and its guards behave as specified: pending and rejected cost
nothing, approval consumes, cancellation restores exactly once, the month resets,
and nobody approves their own.

Dates are pinned to known weekdays rather than derived from `date.today()`,
because a permission may only fall on a working day - a run on a Saturday would
otherwise change whether a request is even accepted.

    docker exec wms-backend-1 pytest tests/test_permissions_phase11.py
"""
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.permissions.models import PermissionRequest, PermissionStatus
from app.modules.users.models import UserRole

# Maps the old `hours` shorthand these tests use onto a period - the allowance
# rules under test here (pending/approved/rejected/cancelled arithmetic) don't
# care which half was picked, only how many hours it costs.
_PERIOD_FOR_HOURS = {1: "first_half_1h", 2: "first_half_2h"}

API = "/api/v1/permission-requests"

# March 2027: Mon 1st through Fri 5th, next Mon the 8th. Far enough out that
# nothing collides with "today".
MON = date(2027, 3, 1)
TUE = date(2027, 3, 2)
WED = date(2027, 3, 3)
THU = date(2027, 3, 4)
FRI = date(2027, 3, 5)
# The SECOND Saturday of March 2027 - genuinely non-working under the company
# calendar. (2027-03-06 is the FIRST Saturday, which the office works.)
SAT = date(2027, 3, 13)
# The FIRST Saturday - an ordinary working day, so a permission may fall on it.
WORKING_SAT = date(2027, 3, 6)
NEXT_MON = date(2027, 3, 8)

# A month boundary that is a working day on both sides: Wed 31 March / Thu 1 April.
MAR_31 = date(2027, 3, 31)
APR_1 = date(2027, 4, 1)


@pytest.fixture()
def team(make_user, make_employee):
    """A project manager, a SECOND project manager (needed to review the first
    one's own permission), and one employee."""
    mu = make_user("mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR", user_id=mu.id)
    m2 = make_user("mgr2@x.com", role=UserRole.project_manager)
    make_employee(employee_code="MGR2", user_id=m2.id)
    eu = make_user("emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP011", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp, "manager_user": mu}


def _remaining(client, login, email="emp@x.com", month: date = MON) -> int:
    """Remaining hours for the month containing `month`.

    Defaults to MON's month rather than to the endpoint's own default, because
    these fixtures live in March 2027 while the endpoint's default is the CURRENT
    business month - reading the default here would silently measure an empty
    month and pass no matter what the derivation did.
    """
    res = client.get(f"{API}/balance/me?month={month.isoformat()}", headers=login(email))
    assert res.status_code == 200, res.text
    return res.json()["remaining_hours"]


def _submit(client, login, day: date, hours: int, email="emp@x.com"):
    return client.post(API, headers=login(email), json={
        "permission_date": day.isoformat(),
        "period": _PERIOD_FOR_HOURS[hours],
        "reason": "School run",
    })


def _approve(client, login, req_id, email="mgr@x.com"):
    return client.post(f"{API}/{req_id}/approve", headers=login(email), json={})


# ======================================================================
# The allowance
# ======================================================================

def test_the_month_starts_with_exactly_four_hours(client, login, team):
    """Sections 12L and 12M - no seeding, no balance row, no setup: the allowance
    is a constant, so an employee with no requests reads 4h.

    Also pins the endpoint's default month, which is what the KPI reads: the
    CURRENT Chennai business month, not a UTC one.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    res = client.get(f"{API}/balance/me", headers=login("emp@x.com"))
    assert res.status_code == 200, res.text
    body = res.json()
    assert (body["allowance_hours"], body["approved_hours"], body["remaining_hours"]) == (
        4, 0, 4,
    )
    assert body["employee_id"] == str(team["employee"].id)
    # Reported as the month's first day, so the client never has to guess it.
    ist_today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
    assert body["month"] == ist_today.replace(day=1).isoformat()


def test_the_worked_example_1h_then_2h_then_1h(client, login, team, db):
    """The business rule verbatim: 4h -> 3h -> 1h -> 0h, and only approvals move
    it. Sections 12A, 12B, 12G and 12N in one walk."""
    assert _remaining(client, login) == 4

    first = _submit(client, login, MON, 1)
    assert first.status_code == 201, first.text
    assert first.json()["status"] == "pending"
    # Section 12E: submitting reserves nothing.
    assert _remaining(client, login) == 4

    assert _approve(client, login, first.json()["id"]).status_code == 200
    assert _remaining(client, login) == 3

    second = _submit(client, login, TUE, 2)
    assert _approve(client, login, second.json()["id"]).status_code == 200
    assert _remaining(client, login) == 1

    third = _submit(client, login, WED, 1)
    assert _approve(client, login, third.json()["id"]).status_code == 200
    assert _remaining(client, login) == 0

    db.expire_all()
    assert db.query(PermissionRequest).filter_by(
        status=PermissionStatus.approved
    ).count() == 3


def test_two_approved_two_hour_permissions_exhaust_the_month(client, login, team):
    """Section 12O."""
    for day in (MON, TUE):
        req = _submit(client, login, day, 2)
        assert _approve(client, login, req.json()["id"]).status_code == 200
    assert _remaining(client, login) == 0


def test_a_rejected_request_costs_nothing(client, login, team, db):
    """Section 12F."""
    req = _submit(client, login, MON, 2)
    res = client.post(f"{API}/{req.json()['id']}/reject", headers=login("mgr@x.com"),
                      json={"comment": "Delivery day"})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"
    assert _remaining(client, login) == 4

    db.expire_all()
    row = db.get(PermissionRequest, res.json()["id"])
    assert row.reviewed_at is not None
    assert row.manager_id == team["manager"].id


# ======================================================================
# Cancellation restores - exactly once
# ======================================================================

def test_cancelling_an_approved_permission_restores_its_hours_once(
    client, login, team, db
):
    """Sections 7, 12H and 12I. There is no stored counter to adjust: the row
    stops being summed, so the restore is exact by construction and the second
    attempt is refused outright.

    The actor is the PROJECT MANAGER. Since Phase 4E an approved permission is a
    granted absence that the employee withdraws through a cancellation request a
    reviewer decides (`test_permission_cancellation.py`); the PM's authority to
    withdraw one outright is unchanged, and it is that path - the one that still
    moves hours in a single step - this test is about.
    """
    req = _submit(client, login, MON, 2).json()
    _approve(client, login, req["id"])
    assert _remaining(client, login) == 2

    first = client.post(f"{API}/{req['id']}/cancel", headers=login("mgr@x.com"))
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "cancelled"
    assert _remaining(client, login) == 4

    # 12I: a second cancellation must not restore again.
    again = client.post(f"{API}/{req['id']}/cancel", headers=login("mgr@x.com"))
    assert again.status_code == 409, again.text
    assert _remaining(client, login) == 4

    db.expire_all()
    assert db.get(PermissionRequest, req["id"]).status == PermissionStatus.cancelled


def test_cancelling_a_pending_request_moves_nothing(client, login, team):
    req = _submit(client, login, MON, 2).json()
    assert client.post(f"{API}/{req['id']}/cancel",
                       headers=login("emp@x.com")).status_code == 200
    assert _remaining(client, login) == 4
    # ...and the freed day accepts a fresh request, since the dead one holds no claim.
    assert _submit(client, login, MON, 1).status_code == 201


def test_a_rejected_request_cannot_then_be_cancelled(client, login, team):
    req = _submit(client, login, MON, 1).json()
    client.post(f"{API}/{req['id']}/reject", headers=login("mgr@x.com"), json={})
    res = client.post(f"{API}/{req['id']}/cancel", headers=login("emp@x.com"))
    assert res.status_code == 409, res.text


# ======================================================================
# Guards
# ======================================================================

def test_approval_is_refused_when_the_month_cannot_cover_it(client, login, team, db):
    """Sections 12C and 12D, and the request survives intact so it can be
    refiled as 1h or rejected."""
    spent = _submit(client, login, MON, 1)
    _approve(client, login, spent.json()["id"])
    spent2 = _submit(client, login, TUE, 2)
    _approve(client, login, spent2.json()["id"])
    assert _remaining(client, login) == 1

    # 12C: 2h against 1h remaining.
    too_big = _submit(client, login, WED, 2).json()
    res = _approve(client, login, too_big["id"])
    assert res.status_code == 422, res.text
    assert "Insufficient permission balance" in res.json()["error"]["message"]
    db.expire_all()
    assert db.get(PermissionRequest, too_big["id"]).status == PermissionStatus.pending
    assert _remaining(client, login) == 1

    # The same day at 1h fits exactly, taking the month to zero...
    client.post(f"{API}/{too_big['id']}/cancel", headers=login("emp@x.com"))
    fits = _submit(client, login, WED, 1).json()
    assert _approve(client, login, fits["id"]).status_code == 200
    assert _remaining(client, login) == 0

    # ...and 12D: 1h against 0h remaining.
    starved = _submit(client, login, THU, 1).json()
    assert _approve(client, login, starved["id"]).status_code == 422
    assert _remaining(client, login) == 0


@pytest.mark.parametrize(
    "period", ["", "3h", "half_hour", "FIRST_HALF_1H", "1_hour", None]
)
def test_only_the_four_period_options_may_be_requested(client, login, team, period):
    """No 30 minutes, no custom duration, no fifth option - refused at the edge
    of the API by the `period` enum (which is what now carries the "no
    30-minute permission" rule `duration_hours: Literal[1, 2]` used to), and the
    DB check constraint refuses an impossible hour count again beneath that
    (see test_the_database_itself_refuses_a_half_hour_permission)."""
    payload = {"permission_date": MON.isoformat(), "reason": "School run"}
    if period is not None:
        payload["period"] = period
    res = client.post(API, headers=login("emp@x.com"), json=payload)
    assert res.status_code == 422, f"{period!r}: {res.text}"


def test_the_database_itself_refuses_a_half_hour_permission(db, team):
    """The rule is an invariant, not a validation - a script bypassing the API
    must still not be able to write one."""
    from sqlalchemy.exc import IntegrityError

    db.add(PermissionRequest(
        employee_id=team["employee"].id, permission_date=MON, duration_hours=0,
        status=PermissionStatus.pending,
    ))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_nobody_approves_their_own_permission_but_another_pm_can(
    client, login, team, db
):
    """Section 12J. The role check alone is not enough: a project manager is an
    employee too and would otherwise spend their own allowance."""
    own = _submit(client, login, MON, 1, email="mgr@x.com").json()

    blocked = _approve(client, login, own["id"])           # the author, a PM
    assert blocked.status_code == 403, blocked.text
    assert "your own permission request" in blocked.json()["error"]["message"]
    db.expire_all()
    assert db.get(PermissionRequest, own["id"]).status == PermissionStatus.pending
    assert _remaining(client, login, email="mgr@x.com") == 4

    # Rejecting your own is the same problem, and equally refused.
    assert client.post(f"{API}/{own['id']}/reject", headers=login("mgr@x.com"),
                       json={}).status_code == 403

    assert _approve(client, login, own["id"], email="mgr2@x.com").status_code == 200
    assert _remaining(client, login, email="mgr@x.com") == 3


def test_an_employee_cannot_review_or_read_someone_elses_request(
    client, login, team, make_employee, make_user, make_permission_request
):
    other_user = make_user("other@x.com", role=UserRole.employee)
    other = make_employee(employee_code="EMP012", user_id=other_user.id)
    theirs = make_permission_request(employee_id=other.id, permission_date=MON)

    h = login("emp@x.com")
    for path in ("approve", "reject"):
        assert client.post(f"{API}/{theirs.id}/{path}", headers=h,
                           json={}).status_code == 403, path
    assert client.post(f"{API}/{theirs.id}/cancel", headers=h).status_code == 403
    assert client.get(f"{API}/{theirs.id}", headers=h).status_code == 403
    # ...and it never appears in their list either.
    assert client.get(API, headers=h).json()["total"] == 0


def test_one_live_request_per_day(client, login, team):
    """Two live asks for one day are a duplicate, not two permissions - otherwise
    each approval would charge the allowance separately for one absence."""
    assert _submit(client, login, MON, 1).status_code == 201
    dup = _submit(client, login, MON, 1)
    assert dup.status_code == 422, dup.text
    assert "already have a pending permission request" in dup.json()["error"]["message"]


def test_a_non_working_day_cannot_have_a_permission(client, login, team):
    """A permission releases hours from inside a working day; a 2nd Saturday has
    none to release. Resolved by the existing company-calendar rules."""
    res = _submit(client, login, SAT, 1)
    assert res.status_code == 422, res.text
    assert "not a working day" in res.json()["error"]["message"]


def test_a_working_saturday_can_have_a_permission(client, login, team):
    """The other half of the same rule: the office works its 1st, 3rd and 5th
    Saturdays, so those DO have hours to release."""
    res = _submit(client, login, WORKING_SAT, 1)
    assert res.status_code == 201, res.text


# ======================================================================
# Month boundary
# ======================================================================

def test_august_usage_does_not_leak_into_september(client, login, team):
    """Section 13 - the month comes from `permission_date`, the business day the
    employee is absent, so 31 March and 1 April are separate allowances and
    unused hours never carry forward."""
    march = _submit(client, login, MAR_31, 2).json()
    assert _approve(client, login, march["id"]).status_code == 200

    assert _remaining(client, login, month=MAR_31) == 2
    # Section 12K / the reset: April is untouched, and is 4h - not 6h.
    assert _remaining(client, login, month=APR_1) == 4

    april = _submit(client, login, APR_1, 2).json()
    assert _approve(client, login, april["id"]).status_code == 200
    assert _remaining(client, login, month=APR_1) == 2
    assert _remaining(client, login, month=MAR_31) == 2


def test_a_full_previous_month_does_not_block_the_next(client, login, team):
    """Section 12K stated the other way round: March spent to zero still leaves
    April able to approve 2h."""
    for day, hours in ((MAR_31, 2), (date(2027, 3, 30), 2)):
        req = _submit(client, login, day, hours).json()
        assert _approve(client, login, req["id"]).status_code == 200
    assert _remaining(client, login, month=MAR_31) == 0

    april = _submit(client, login, APR_1, 2).json()
    assert _approve(client, login, april["id"]).status_code == 200
    assert _remaining(client, login, month=APR_1) == 2


# ======================================================================
# Transaction safety
# ======================================================================

def test_an_approval_locks_the_whole_month_not_just_its_own_row(
    client, login, team, make_permission_request
):
    """Section 12Q. The race that matters is two DIFFERENT pending requests being
    approved at the same instant: each would read the same remaining hours and
    both be allowed, taking the month negative. `lock_month` is what stops that,
    so this proves the lock really covers the month and really is exclusive - a
    second session cannot take it while the first holds it.
    """
    from app.core.database import SessionLocal
    from app.modules.permissions.balance import lock_month

    make_permission_request(employee_id=team["employee"].id, permission_date=MON)
    make_permission_request(employee_id=team["employee"].id, permission_date=TUE)

    holder = SessionLocal()
    waiter = SessionLocal()
    try:
        lock_month(holder, team["employee"].id, MON)   # held until commit/rollback
        waiter.execute(text("SET LOCAL lock_timeout = '400ms'"))
        # Locking via TUE resolves to the same month, so the second writer
        # contends even though it targets a different row.
        with pytest.raises(OperationalError):
            lock_month(waiter, team["employee"].id, TUE)
    finally:
        waiter.rollback()
        waiter.close()
        holder.rollback()
        holder.close()


def test_a_refused_approval_leaves_nothing_behind(client, login, team, db):
    """The insufficient-balance path raises before anything is written, so the
    request stays pending, the balance is unmoved and no reviewer is recorded."""
    spent = _submit(client, login, MON, 2).json()
    _approve(client, login, spent["id"])
    spent2 = _submit(client, login, TUE, 2).json()
    _approve(client, login, spent2["id"])

    starved = _submit(client, login, WED, 1).json()
    assert _approve(client, login, starved["id"]).status_code == 422

    db.expire_all()
    row = db.get(PermissionRequest, starved["id"])
    assert (row.status, row.manager_id, row.reviewed_at) == (
        PermissionStatus.pending, None, None,
    )
    assert _remaining(client, login) == 0


# ======================================================================
# The attendance boundary (foundation only - Phase 12 owns the integration)
# ======================================================================

def test_an_approved_permission_writes_no_attendance_and_keeps_the_day_present(
    client, login, team, make_attendance, db
):
    """Section 8. The status stays `present` and the hours live separately, so a
    day reads "Present" plus 1h - never a `present_1h` status. Phase 11 only
    guarantees the two facts can be joined; it does not join them.
    """
    make_attendance(
        employee_id=team["employee"].id, attendance_date=MON,
        status=AttendanceStatus.present, total_minutes=426,
    )
    req = _submit(client, login, MON, 1).json()
    assert _approve(client, login, req["id"]).status_code == 200

    db.expire_all()
    rows = db.query(AttendanceRecord).filter_by(employee_id=team["employee"].id).all()
    assert len(rows) == 1
    assert (rows[0].attendance_date, rows[0].status, rows[0].total_minutes) == (
        MON, AttendanceStatus.present, 426,
    )
    # The hours are retrievable for that employee-day - the Phase 12 hook.
    approved = db.query(PermissionRequest).filter_by(
        employee_id=team["employee"].id, permission_date=MON,
        status=PermissionStatus.approved,
    ).one()
    assert approved.duration_hours == 1


# ======================================================================
# Audit
# ======================================================================

def test_every_permission_event_lands_in_the_central_audit_log(
    client, login, team, db
):
    """Section 11 - the existing audit architecture, not a second one. The
    balance is derived, so `details` is the only written record of the movement.
    """
    from app.modules.audit.models import AuditLog

    req = _submit(client, login, MON, 2).json()
    _approve(client, login, req["id"])
    # The PM's outright withdrawal - the one-step path that still moves hours
    # since Phase 4E. See `test_permission_cancellation.py` for the audit trail
    # of the employee's three-step request.
    client.post(f"{API}/{req['id']}/cancel", headers=login("mgr@x.com"))

    rejected = _submit(client, login, TUE, 1).json()
    client.post(f"{API}/{rejected['id']}/reject", headers=login("mgr@x.com"), json={})

    db.expire_all()
    rows = db.query(AuditLog).filter(
        AuditLog.entity_type == "permission_request"
    ).all()
    actions = {r.action for r in rows}
    assert {
        "permission.request.submit",
        "permission.request.approve",
        "permission.request.reject",
        "permission.request.cancel",
    } == actions

    approve = next(r for r in rows if r.action == "permission.request.approve")
    assert approve.details["duration_hours"] == 2
    assert approve.details["month"] == "2027-03"
    assert (approve.details["remaining_before"], approve.details["remaining_after"]) == (4, 2)

    cancel = next(r for r in rows if r.action == "permission.request.cancel")
    assert (cancel.details["remaining_before"], cancel.details["remaining_after"]) == (2, 4)
