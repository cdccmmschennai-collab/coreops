"""Phase 3B: what an approved half-day leave COSTS, and what withdrawing it
gives back.

WHAT THIS PINS DOWN
===================
The complete accounting path, walked through the real endpoints rather than the
pricing helper:

    balance 3.0
      -> POST /leave-requests            (half_day_period = first_half)
      -> POST .../approve                balance 2.5
      -> POST .../request-cancellation    balance 2.5   (still taken)
      -> POST .../approve-cancellation    balance 3.0
                 or reject-cancellation   balance 2.5

`test_leave_half_day.py` already owns the pricing rule against synthetic rows and
`test_leave_half_day_approval_attendance.py` owns the row an approval writes.
What is asserted HERE is the number an employee actually has left after the
service has run - the thing neither of those two can see on its own.

WHERE THE ARITHMETIC LIVES
==========================
Nowhere new. There is one pricing rule (`ledger.leave_days_for`) and one
consumption rule (an `attendance_records` row), so approving a half day costs 0.5
because the row it wrote SAYS 0.5, and cancelling it restores 0.5 because that
row is deleted. Nothing adds, subtracts or stores a balance, which is why no test
below has to check for double-crediting: there is no counter to double-credit.

THE DISTINCTION THAT DECIDES EVERYTHING
=======================================
Employee leave and a company-wide half day are the SAME attendance status. The
quantity is the whole difference:

    employee half-day leave   half_day, leave_day_fraction 0.5   costs 0.5
    company-wide half day     half_day, leave_day_fraction NULL  costs 0

so every assertion here is about a fraction and a balance, never about a status,
and the last section exists solely to prove a cancellation cannot reach an office
half day.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_balance.py
"""
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.leave import email as leave_email
from app.modules.leave.effects import reverse_leave_approved
from app.modules.leave.models import LeaveHalfDayPeriod, LeaveStatus
from app.modules.leave_balances import ledger
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult
from app.shared.leave_units import is_half_step

API = "/api/v1/leave-requests"

# One month, so every request below is weighed against the same balance and the
# carry-forward chain never enters the picture. March 2027 is far enough out that
# no real calendar collides with it.
MAR = date(2027, 3, 1)

# Five separate working days in that month - Wednesdays, plus one Friday - so no
# two requests overlap and each can be approved and withdrawn independently.
D1 = date(2027, 3, 3)
D2 = date(2027, 3, 10)
D3 = date(2027, 3, 17)
D4 = date(2027, 3, 24)
D5 = date(2027, 3, 5)

# A day the OFFICE closed at noon. In the same month, so it is inside every
# balance read below, and on no request's range.
COMPANY_HALF = date(2027, 3, 12)

# The starting balance the brief is written in terms of.
OPENING = Decimal("3.00")


class _Recorder:
    """Stands in for `enqueue_email` so nothing here depends on a mailer."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return EnqueueResult(queued=True, task_id="task-1", recipients=())


@pytest.fixture()
def mailer(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(leave_email, "enqueue_email", rec)
    return rec


@pytest.fixture()
def team(make_user, make_employee):
    """A reviewing PM and the requesting employee - the ordinary approval pair."""
    pm_user = make_user("h3b-pm@x.com", role=UserRole.project_manager)
    make_employee(
        employee_code="H3BPM", first_name="Priya", last_name="M",
        user_id=pm_user.id, work_email="priya.m@cdccmms.com",
    )
    emp_user = make_user("h3b-emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="H3BEMP", first_name="Arun", last_name="K",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
        work_email="arun.k@cdccmms.com",
    )
    return {"pm_user": pm_user, "employee": emp, "employee_user": emp_user}


@pytest.fixture()
def funded(team, make_leave_adjustment):
    """The employee, opening March with exactly 3 days and no monthly accrual.

    Seeded as an adjustment rather than an allocation on purpose: an allocation
    would also accrue in April and every month after, and these tests are about
    what leaves the pool, not what enters it. With no allocation row, March's
    balance is the adjustment minus what March consumed - and nothing else.
    """
    employee = team["employee"]
    make_leave_adjustment(
        employee_id=employee.id, effective_month=MAR, days="3",
        reason="Opening balance",
    )
    return employee


# ---------- the calls under test --------------------------------------------

def _balance(db, employee_id) -> Decimal:
    """March's Available Leave, straight from the single authority."""
    db.expire_all()
    return ledger.closing_balance(db, employee_id, MAR)


def _create(client, login, *, start, end=None, period=None):
    body = {
        "start_date": start.isoformat(),
        "end_date": (end or start).isoformat(),
        "reason": "Personal",
    }
    if period is not None:
        body["half_day_period"] = period
    res = client.post(API, headers=login("h3b-emp@x.com"), json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _approve(client, login, req_id):
    res = client.post(f"{API}/{req_id}/approve", headers=login("h3b-pm@x.com"), json={})
    assert res.status_code == 200, res.text
    return res.json()


def _take(client, login, *, start, end=None, period=None):
    """File and approve one leave - the whole of what spends the balance."""
    req_id = _create(client, login, start=start, end=end, period=period)
    _approve(client, login, req_id)
    return req_id


def _ask_to_withdraw(client, login, req_id):
    res = client.post(
        f"{API}/{req_id}/request-cancellation", headers=login("h3b-emp@x.com")
    )
    assert res.status_code == 200, res.text
    return res.json()


def _decide_withdrawal(client, login, req_id, decision):
    res = client.post(f"{API}/{req_id}/{decision}", headers=login("h3b-pm@x.com"))
    assert res.status_code == 200, res.text
    return res.json()


# ======================================================================
# PART A - an approved half day costs exactly half a day
# ======================================================================

@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_approving_a_half_day_spends_exactly_half_a_day(
    client, login, db, funded, mailer, period,
):
    """THE PHASE, in one line: 3.0 -> 2.5.

    Parametrised over both halves because which half was taken changes the NAME
    of the leave and nothing about its price - an accidental per-variant fraction
    would show up here as 3.0 -> something else for one of the two.
    """
    assert _balance(db, funded.id) == OPENING

    _take(client, login, start=D1, period=period)

    assert _balance(db, funded.id) == Decimal("2.50")


def test_two_half_days_on_different_dates_cost_one_day(
    client, login, db, funded, mailer,
):
    """3.0 -> 2.5 -> 2.0. Two halves are a day, and the second is weighed against
    a balance the first has already reduced."""
    assert _balance(db, funded.id) == OPENING

    _take(client, login, start=D1, period="first_half")
    assert _balance(db, funded.id) == Decimal("2.50")

    _take(client, login, start=D2, period="second_half")
    assert _balance(db, funded.id) == Decimal("2.00")


def test_three_half_days_do_not_drift(client, login, db, funded, mailer):
    """3.0 -> 2.5 -> 2.0 -> 1.5. The step is the same every time; a fold that
    accumulated error would land on 1.4999... or 1.51 by the third."""
    _take(client, login, start=D1, period="first_half")
    _take(client, login, start=D2, period="second_half")
    _take(client, login, start=D3, period="first_half")

    assert _balance(db, funded.id) == Decimal("1.50")


def test_a_full_day_leave_still_costs_a_whole_day(client, login, db, funded, mailer):
    """3.0 -> 2.0. THE REGRESSION THIS PHASE IS MOST AT RISK OF.

    Filed on a single day, exactly like a half day and differing only by the
    absent half, so it also proves the price is read from the request rather than
    from the number of days.
    """
    assert _balance(db, funded.id) == OPENING

    _take(client, login, start=D1)

    assert _balance(db, funded.id) == Decimal("2.00")


def test_a_company_wide_half_day_is_still_free(
    client, login, db, funded, mailer, make_attendance,
):
    """The office closing at noon costs the employee nothing, before or after a
    half-day leave of their own elsewhere in the month.

    Both rows read `half_day`. If anything anywhere priced that status rather
    than the stated quantity, this employee would be charged 1.0 instead of 0.5.
    """
    make_attendance(
        employee_id=funded.id, attendance_date=COMPANY_HALF,
        status=AttendanceStatus.half_day, leave_day_fraction=None,
    )
    assert _balance(db, funded.id) == OPENING

    _take(client, login, start=D1, period="first_half")

    # 3.0 - 0.5, not 3.0 - 1.0: the company's half day added nothing.
    assert _balance(db, funded.id) == Decimal("2.50")


# ======================================================================
# PART B - the arithmetic is Decimal, and stays on the half step
# ======================================================================

def test_the_balance_walks_down_in_exact_half_steps(
    client, login, db, funded, mailer,
):
    """3.0 -> 2.5 -> 2.0 -> 1.5 -> 1.0 -> 0.5, every figure a valid quantity of
    leave.

    Five approvals in a row is where binary floating point would show: 0.1 + 0.2
    is not 0.3, and a balance folded in floats drifts off the half step long
    before it reaches 0.5. Each figure is checked to BE a half step by the same
    shared rule the API validates corrections with, so "0.4999999" fails as
    loudly as a wrong answer would.
    """
    expected = [
        Decimal("3.00"), Decimal("2.50"), Decimal("2.00"),
        Decimal("1.50"), Decimal("1.00"), Decimal("0.50"),
    ]
    seen = [_balance(db, funded.id)]
    for day in (D1, D2, D3, D4, D5):
        _take(client, login, start=day, period="first_half")
        seen.append(_balance(db, funded.id))

    assert seen == expected
    for value in seen:
        assert isinstance(value, Decimal), "the ledger must not hand back a float"
        assert is_half_step(value), f"{value} is not a whole number of half days"


def test_the_marked_row_states_the_fraction_as_an_exact_decimal(
    client, login, db, funded, mailer,
):
    """The 0.5 the balance is derived FROM is a Decimal on the row, not a float
    the ledger has to interpret. `Decimal("0.5") == 0.5` is true, so the type is
    asserted separately from the value."""
    _take(client, login, start=D1, period="first_half")

    db.expire_all()
    row = (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one()
    )
    assert isinstance(row.leave_day_fraction, Decimal)
    assert row.leave_day_fraction == Decimal("0.5")


# ======================================================================
# PART C - withdrawing an approved half day gives back exactly its half
# ======================================================================

@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_an_approved_cancellation_restores_the_half(
    client, login, db, funded, mailer, period,
):
    """3.0 -> 2.5 -> 3.0. THE OTHER HALF OF THE PHASE.

    Before this phase the reversal looked for `leave` rows only, so the
    `half_day` row survived the cancellation and the employee stayed charged
    0.5 for leave they never took.
    """
    req_id = _take(client, login, start=D1, period=period)
    assert _balance(db, funded.id) == Decimal("2.50")

    _ask_to_withdraw(client, login, req_id)
    # Asking is not withdrawing: the absence still stands until a reviewer rules.
    assert _balance(db, funded.id) == Decimal("2.50")

    decided = _decide_withdrawal(client, login, req_id, "approve-cancellation")

    assert decided["status"] == "cancelled"
    assert decided["half_day_period"] == period
    assert _balance(db, funded.id) == OPENING


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_the_restored_day_leaves_no_attendance_row_behind(
    client, login, db, funded, mailer, period,
):
    """The restore IS the deletion - there is no balance to put back - so the row
    being gone and the balance being back are the same fact, asserted together."""
    req_id = _take(client, login, start=D1, period=period)
    _ask_to_withdraw(client, login, req_id)
    _decide_withdrawal(client, login, req_id, "approve-cancellation")

    db.expire_all()
    assert (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one_or_none()
        is None
    )
    assert _balance(db, funded.id) == OPENING


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_a_rejected_cancellation_restores_nothing(
    client, login, db, funded, mailer, period,
):
    """3.0 -> 2.5 -> 2.5. The reviewer kept the leave, so the employee keeps
    paying for it and the day stays on the calendar."""
    req_id = _take(client, login, start=D1, period=period)
    assert _balance(db, funded.id) == Decimal("2.50")

    _ask_to_withdraw(client, login, req_id)
    decided = _decide_withdrawal(client, login, req_id, "reject-cancellation")

    assert decided["status"] == "approved"
    assert _balance(db, funded.id) == Decimal("2.50")
    db.expire_all()
    row = (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one()
    )
    assert row.status is AttendanceStatus.half_day
    assert row.leave_day_fraction == Decimal("0.5")


def test_a_full_day_cancellation_still_restores_the_whole_day(
    client, login, db, funded, mailer,
):
    """3.0 -> 2.0 -> 3.0. Teaching the reversal about halves did not change what
    it does with a whole day: it still identifies a `leave` row by its status
    alone, whatever fraction that row does or does not state."""
    req_id = _take(client, login, start=D1)
    assert _balance(db, funded.id) == Decimal("2.00")

    _ask_to_withdraw(client, login, req_id)
    _decide_withdrawal(client, login, req_id, "approve-cancellation")

    assert _balance(db, funded.id) == OPENING
    db.expire_all()
    assert (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one_or_none()
        is None
    )


def test_cancelling_one_half_day_does_not_restore_another(
    client, login, db, funded, mailer,
):
    """Two half days taken, one withdrawn: 3.0 -> 2.5 -> 2.0 -> 2.5, not 3.0.

    A reversal removes the days of ITS OWN range, so the credit can only ever be
    what that request actually cost.
    """
    first = _take(client, login, start=D1, period="first_half")
    _take(client, login, start=D2, period="second_half")
    assert _balance(db, funded.id) == Decimal("2.00")

    _ask_to_withdraw(client, login, first)
    _decide_withdrawal(client, login, first, "approve-cancellation")

    assert _balance(db, funded.id) == Decimal("2.50")


def test_a_half_day_the_pm_has_since_edited_is_neither_removed_nor_refunded(
    client, login, db, funded, mailer,
):
    """The narrow-removal rule, which halves inherit unchanged.

    Once a human puts a time on the day it is their decision, so the cancellation
    leaves it standing - and because the row is still there the ledger is still
    counting it, which is exactly the symmetry that makes over-restoring
    impossible.
    """
    req_id = _take(client, login, start=D1, period="first_half")
    db.expire_all()
    row = (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one()
    )
    row.check_in_at = datetime(2027, 3, 3, 4, 0, tzinfo=timezone.utc)
    db.commit()

    _ask_to_withdraw(client, login, req_id)
    _decide_withdrawal(client, login, req_id, "approve-cancellation")

    db.expire_all()
    kept = (
        db.query(AttendanceRecord)
        .filter_by(employee_id=funded.id, attendance_date=D1)
        .one_or_none()
    )
    assert kept is not None, "a day a human has ruled on is never deleted"
    assert _balance(db, funded.id) == Decimal("2.50")


# ======================================================================
# The company-wide half day is out of a cancellation's reach
# ======================================================================

def test_a_cancellation_cannot_delete_a_company_half_day(
    db, funded, team, make_leave_request, make_attendance,
):
    """THE REASON THE FRACTION IS PART OF THE MATCH.

    Driven at `reverse_leave_approved` directly because the API cannot reach this
    state - a request may not even be FILED for a day already marked `half_day`
    (`_worked_attendance_dates`) - and the match rule must still be right
    underneath that guard rather than only because of it.

    The row is the same status the reversal is now looking for and states NO
    quantity, so matching `half_day` alone would delete the office's own half day
    and credit the employee 0.5 they never spent.
    """
    company = make_attendance(
        employee_id=funded.id, attendance_date=D1,
        status=AttendanceStatus.half_day, leave_day_fraction=None,
    )
    company_id = company.id
    req = make_leave_request(
        employee_id=funded.id, start_date=D1, end_date=D1,
        status=LeaveStatus.approved,
    )
    req.half_day_period = LeaveHalfDayPeriod.first_half
    db.commit()

    effect = reverse_leave_approved(db, team["pm_user"], req)
    db.commit()

    assert effect.days == [], "nothing of this request's was ever marked"
    assert effect.skipped == [D1]
    db.expire_all()
    untouched = db.get(AttendanceRecord, company_id)
    assert untouched is not None
    assert untouched.status is AttendanceStatus.half_day
    assert untouched.leave_day_fraction is None
    # And it never cost anything, so nothing was credited back either.
    assert _balance(db, funded.id) == OPENING
