"""Phase 3A: what APPROVING a half-day leave writes to the calendar.

WHAT THIS PINS DOWN
===================
One branch, in one place. `effects.apply_leave_approved` writes::

    half_day_period is not NULL  ->  status = half_day, leave_day_fraction = 0.5
    half_day_period is NULL      ->  status = leave,    leave_day_fraction = NULL

and nothing else about an approval differs between the two. The full-day row is
asserted here as well as in `test_leave_phase10.py`, because the value of this
phase is precisely that the day a full-day leave writes did NOT move.

THE DISTINCTION THAT MATTERS
============================
`half_day` is the status of BOTH an employee's half-day leave and a company-wide
half day - they are the same attendance fact, the employee worked half the day.
The QUANTITY is what separates them:

    employee half-day leave   status half_day, leave_day_fraction 0.5
    company-wide half day     status half_day, leave_day_fraction NULL

so the tests below check the fraction, never the status alone, and one of them
exists only to prove an existing company half day is not swept up by an
approval happening elsewhere in the same month.

NOT ASSERTED HERE: no balance, KPI or ledger expectation.
`test_leave_half_day.py` owns the pricing rule, `test_leave_half_day_balance.py`
owns what an approval and its withdrawal do to the balance (Phase 3B), and this
file owns only the row that is written.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_approval_attendance.py
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.leave import email as leave_email
from app.modules.leave.models import LeaveHalfDayPeriod, LeaveRequest, LeaveStatus
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

API = "/api/v1/leave-requests"

# Plain working days in 2027 - far enough out that no real calendar collides
# with them, and each one used by exactly one test so no two ranges overlap.
HALF_FIRST = date(2027, 3, 3)    # Wednesday
HALF_SECOND = date(2027, 3, 10)  # Wednesday
FULL_START = date(2027, 3, 15)   # Monday
FULL_END = date(2027, 3, 17)     # Wednesday
COMPANY_HALF = date(2027, 2, 10)  # Wednesday, and nowhere near any range above


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
    pm_user = make_user("h3a-pm@x.com", role=UserRole.project_manager)
    make_employee(
        employee_code="H3APM", first_name="Priya", last_name="M",
        user_id=pm_user.id, work_email="priya.m@cdccmms.com",
    )
    emp_user = make_user("h3a-emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="H3AEMP", first_name="Arun", last_name="K",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
        work_email="arun.k@cdccmms.com",
    )
    return {"pm_user": pm_user, "employee": emp}


def _create(client, login, *, start, end, period=None):
    body = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "reason": "Personal",
    }
    if period is not None:
        body["half_day_period"] = period
    res = client.post(API, headers=login("h3a-emp@x.com"), json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _approve(client, login, req_id):
    res = client.post(f"{API}/{req_id}/approve", headers=login("h3a-pm@x.com"), json={})
    assert res.status_code == 200, res.text
    return res.json()


def _rows(db, employee_id) -> list[AttendanceRecord]:
    return (
        db.query(AttendanceRecord)
        .filter_by(employee_id=employee_id)
        .order_by(AttendanceRecord.attendance_date)
        .all()
    )


def _marked(db, employee_id, day) -> AttendanceRecord:
    row = (
        db.query(AttendanceRecord)
        .filter_by(employee_id=employee_id, attendance_date=day)
        .one_or_none()
    )
    assert row is not None, f"no attendance row written for {day}"
    return row


# ======================================================================
# 1-2. Either half writes the same row
# ======================================================================

@pytest.mark.parametrize(
    ("day", "period"),
    [
        pytest.param(HALF_FIRST, "first_half", id="first-half"),
        pytest.param(HALF_SECOND, "second_half", id="second-half"),
    ],
)
def test_approving_a_half_day_marks_the_day_half_day_at_0_5(
    client, login, db, team, mailer, day, period,
):
    """THE PHASE. One working day, status `half_day`, fraction exactly 0.5.

    Parametrised over both halves on purpose: which half was taken changes the
    NAME of the leave and nothing about what it costs, so a single expectation
    covers both and an accidental per-variant fraction would fail here.
    """
    req_id = _create(client, login, start=day, end=day, period=period)
    _approve(client, login, req_id)

    db.expire_all()
    rows = _rows(db, team["employee"].id)
    assert len(rows) == 1, "a half-day leave is one day, not two"

    row = rows[0]
    assert row.attendance_date == day
    assert row.status is AttendanceStatus.half_day
    assert row.leave_day_fraction == Decimal("0.5")
    # The same "no fabricated times" rule a full-day leave row follows.
    assert (row.check_in_at, row.check_out_at, row.total_minutes) == (None, None, 0)


@pytest.mark.parametrize(
    ("day", "period"),
    [
        pytest.param(HALF_FIRST, "first_half", id="first-half"),
        pytest.param(HALF_SECOND, "second_half", id="second-half"),
    ],
)
def test_the_approved_request_still_says_which_half(
    client, login, db, team, mailer, day, period,
):
    """The half survives the approval, on the row and on the wire.

    The attendance record deliberately does NOT carry the half - a day is half
    a day whichever half it was - so `leave_requests.half_day_period` stays the
    only place that fact lives, and losing it here would make the request
    unnameable afterwards.
    """
    req_id = _create(client, login, start=day, end=day, period=period)
    body = _approve(client, login, req_id)

    assert body["status"] == "approved"
    assert body["half_day_period"] == period

    db.expire_all()
    row = db.get(LeaveRequest, req_id)
    assert row.status is LeaveStatus.approved
    assert row.half_day_period is LeaveHalfDayPeriod(period)


# ======================================================================
# 3. Full-day leave is untouched
# ======================================================================

def test_full_day_approval_still_writes_plain_leave_days(
    client, login, db, team, mailer,
):
    """THE REGRESSION THIS PHASE IS MOST AT RISK OF.

    Mon-Wed, no half named: three `leave` rows STATING NO FRACTION, exactly as
    before migration 0083 existed. A fraction written here - even the correct
    1 - would be a new value on a row the ledger already prices by its status,
    so the absence is the assertion.
    """
    req_id = _create(client, login, start=FULL_START, end=FULL_END)
    body = _approve(client, login, req_id)
    assert body["half_day_period"] is None

    db.expire_all()
    rows = _rows(db, team["employee"].id)
    assert [r.attendance_date for r in rows] == [
        FULL_START, date(2027, 3, 16), FULL_END,
    ]
    for row in rows:
        assert row.status is AttendanceStatus.leave
        assert row.leave_day_fraction is None


def test_a_single_full_day_is_not_mistaken_for_a_half(
    client, login, db, team, mailer,
):
    """A one-day full-day leave has the same SHAPE as a half day - one working
    day, Normal classification - and differs only by the absent half. It must
    still be a whole `leave` day, so the branch is proven to read
    `half_day_period` and not the day count."""
    req_id = _create(client, login, start=HALF_FIRST, end=HALF_FIRST)
    _approve(client, login, req_id)

    db.expire_all()
    row = _marked(db, team["employee"].id, HALF_FIRST)
    assert row.status is AttendanceStatus.leave
    assert row.leave_day_fraction is None


# ======================================================================
# 4. The company-wide half day is a different thing and stays one
# ======================================================================

def test_an_existing_company_half_day_is_not_charged_by_an_approval(
    client, login, db, team, mailer, make_attendance,
):
    """A company half day states NO fraction, and an approval elsewhere in the
    calendar leaves it exactly so.

    This is the only reason the fraction column exists: both rows read
    `half_day`, so if an approval reached for the status it would silently start
    charging the employee for an office that closed at noon. It writes only the
    days of its own request, and states the quantity only on those.
    """
    company = make_attendance(
        employee_id=team["employee"].id,
        attendance_date=COMPANY_HALF,
        status=AttendanceStatus.half_day,
        leave_day_fraction=None,
    )
    company_id = company.id

    req_id = _create(client, login, start=HALF_FIRST, end=HALF_FIRST,
                     period="first_half")
    _approve(client, login, req_id)

    db.expire_all()
    untouched = db.get(AttendanceRecord, company_id)
    assert untouched is not None, "an approval must never delete another day"
    assert untouched.attendance_date == COMPANY_HALF
    assert untouched.status is AttendanceStatus.half_day
    assert untouched.leave_day_fraction is None

    # And the two now coexist, told apart by the quantity alone.
    leave_day = _marked(db, team["employee"].id, HALF_FIRST)
    assert leave_day.status is AttendanceStatus.half_day
    assert leave_day.leave_day_fraction == Decimal("0.5")
