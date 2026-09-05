"""Withdrawing APPROVED leave, for every kind of leave there is.

WHAT THIS PINS DOWN
===================
The cancellation workflow is one workflow. A Normal leave, a Special leave and
either half of a half day all travel the identical path:

    approved -> cancellation_requested   the employee asks
    cancellation_requested -> cancelled  a reviewer approves the withdrawal
    cancellation_requested -> approved   a reviewer keeps the leave

Nothing in `service.py` branches on `half_day_period` anywhere along it, and that
is the property these tests exist to hold: no second cancellation system was
introduced for half days, the half is simply CARRIED so that every screen deciding
the withdrawal can NAME the request the employee actually filed. The full-day
behaviour those same paths already had is asserted in `test_leave_cancellation.py`
and is untouched here.

AUTHORISATION IS THE BACKEND'S
==============================
The detail page now offers Approve cancellation / Keep approved leave, so the
tests that matter most are the ones proving the buttons are not what stops the
wrong person: `_assert_can_review` refuses the request's own author (a PM and a
Head file their own leave too) and anybody who is neither a PM nor the routed
project's Head, on both decision endpoints.

STILL OUT OF SCOPE (Phase 3): no `half_day` attendance row, no
`leave_day_fraction`, no balance movement. Nothing here asserts what a half-day
approval writes to attendance, because that is deliberately still what a full-day
approval writes.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_cancellation.py
"""
from datetime import date, timedelta

import pytest

from app.modules.leave import email as leave_email
from app.modules.leave.classification import LeaveClassification
from app.modules.leave.models import (
    LeaveHalfDayPeriod,
    LeaveRequest,
    LeaveStatus,
    leave_type_label,
)
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

API = "/api/v1/leave-requests"

# Working Wednesdays far enough out that no real calendar collides with them and
# every request is still entirely ahead of today - a finished absence has nothing
# left to withdraw, which is the one rule that reads the clock.
HALF_DAY = date(2027, 3, 3)
NORMAL_DAY = date(2027, 3, 10)
# A fortnight - more than 3 working days on any office calendar, so Special.
SPECIAL_START = date(2027, 4, 5)
SPECIAL_END = SPECIAL_START + timedelta(days=13)


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
    """A reviewing PM, the requesting employee, and an unrelated employee.

    The third one is what makes the authorisation tests mean something: somebody
    who is signed in, has an employee record, and is neither a project manager
    nor the routed project's Head.
    """
    pm_user = make_user("hdc-pm@x.com", role=UserRole.project_manager)
    pm = make_employee(
        employee_code="HDCPM", first_name="Priya", last_name="M",
        user_id=pm_user.id, work_email="priya.m@cdccmms.com",
    )
    emp_user = make_user("hdc-emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="HDCEMP", first_name="Sowrish Kumar", last_name="S",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
        work_email="sowrish.s@cdccmms.com",
    )
    other_user = make_user("hdc-other@x.com", role=UserRole.employee)
    other = make_employee(
        employee_code="HDCOTH", first_name="Vikram", last_name="R",
        user_id=other_user.id, reporting_pm_id=pm_user.id,
    )
    return {
        "pm_user": pm_user, "pm": pm,
        "employee": emp, "employee_user": emp_user,
        "other": other, "other_user": other_user,
    }


# ---------- the one path, walked for each kind of leave ----------------------

def _create(client, login, *, start, end, period=None):
    body = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "reason": "Personal",
    }
    if period is not None:
        body["half_day_period"] = period
    res = client.post(API, headers=login("hdc-emp@x.com"), json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _approve(client, login, req_id):
    res = client.post(f"{API}/{req_id}/approve", headers=login("hdc-pm@x.com"), json={})
    assert res.status_code == 200, res.text
    return res.json()


def _ask_to_withdraw(client, login, req_id, email="hdc-emp@x.com"):
    return client.post(f"{API}/{req_id}/request-cancellation", headers=login(email))


def _approved_request(client, login, *, start, end, period=None):
    """Approved leave of the requested shape, ready to be withdrawn."""
    req_id = _create(client, login, start=start, end=end, period=period)
    _approve(client, login, req_id)
    return req_id


# The four kinds of leave a cancellation has to serve, named as the brief names
# them. `period` is what makes the last two half days; everything else is equal.
LEAVE_SHAPES = [
    pytest.param(NORMAL_DAY, NORMAL_DAY, None, id="normal"),
    pytest.param(SPECIAL_START, SPECIAL_END, None, id="special"),
    pytest.param(HALF_DAY, HALF_DAY, "first_half", id="half-day-first"),
    pytest.param(HALF_DAY, HALF_DAY, "second_half", id="half-day-second"),
]


@pytest.mark.parametrize(("start", "end", "period"), LEAVE_SHAPES)
def test_4_7_approved_leave_of_every_kind_can_ask_for_cancellation(
    client, login, db, team, mailer, start, end, period,
):
    """Requirements 4-7. One path, four shapes, no branch between them."""
    req_id = _approved_request(client, login, start=start, end=end, period=period)

    res = _ask_to_withdraw(client, login, req_id)

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancellation_requested"
    row = db.get(LeaveRequest, req_id)
    assert row.status is LeaveStatus.cancellation_requested


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_8_the_cancellation_preserves_the_half(client, login, db, team, mailer, period):
    """Requirement 8. THE CENTRAL ASSERTION.

    The employee's choice of half is not re-derived, defaulted or dropped at any
    step of the withdrawal - it is the same stored value from creation through to
    the cancelled row, which is the whole precondition for naming it correctly on
    the queue and on the detail page.
    """
    expected = LeaveHalfDayPeriod(period)
    req_id = _approved_request(client, login, start=HALF_DAY, end=HALF_DAY, period=period)
    assert db.get(LeaveRequest, req_id).half_day_period is expected

    asked = _ask_to_withdraw(client, login, req_id)
    assert asked.status_code == 200, asked.text
    assert asked.json()["half_day_period"] == period
    assert db.get(LeaveRequest, req_id).half_day_period is expected

    decided = client.post(
        f"{API}/{req_id}/approve-cancellation", headers=login("hdc-pm@x.com")
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "cancelled"
    assert decided.json()["half_day_period"] == period
    row = db.get(LeaveRequest, req_id)
    assert row.status is LeaveStatus.cancelled
    assert row.half_day_period is expected
    # And the single-date shape it was filed with is intact - a withdrawal never
    # widens a half day into a day.
    assert row.start_date == row.end_date == HALF_DAY


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_8b_keeping_the_leave_preserves_the_half_too(
    client, login, db, team, mailer, period,
):
    """The other decision returns the request to `approved`, unchanged in every
    respect including the half - the original approval is untouched."""
    req_id = _approved_request(client, login, start=HALF_DAY, end=HALF_DAY, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.post(
        f"{API}/{req_id}/reject-cancellation", headers=login("hdc-pm@x.com")
    )

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert res.json()["half_day_period"] == period
    row = db.get(LeaveRequest, req_id)
    assert row.status is LeaveStatus.approved
    assert row.half_day_period is LeaveHalfDayPeriod(period)


# ---------- 9-10. what the queue and the detail page are given to show -------

@pytest.mark.parametrize(
    ("period", "label"),
    [("first_half", "Half Day (First)"), ("second_half", "Half Day (Second)")],
)
def test_9_the_cancellation_queue_row_carries_the_half(
    client, login, team, mailer, period, label,
):
    """Requirement 9. `GET /leave-requests?status=cancellation_requested` is the
    Cancellation Requests list's own query, and the half is on its rows - so the
    Type cell composes "Half Day (First)" rather than the Normal the request also
    classifies as."""
    req_id = _approved_request(client, login, start=HALF_DAY, end=HALF_DAY, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.get(
        f"{API}?status=cancellation_requested", headers=login("hdc-pm@x.com")
    )

    assert res.status_code == 200, res.text
    rows = [r for r in res.json()["items"] if r["id"] == req_id]
    assert len(rows) == 1
    row = rows[0]
    assert row["half_day_period"] == period
    # It classifies Normal - one working day is <= 3 - and is still displayed as
    # the half. That precedence is `leave_type_label`, shared with the emails and
    # mirrored by `types.ts::leaveTypeLabel` for the table itself.
    assert row["classification"] == "normal"
    assert leave_type_label(LeaveClassification(row["classification"]),
                            LeaveHalfDayPeriod(row["half_day_period"])) == label


@pytest.mark.parametrize(
    ("period", "label"),
    [("first_half", "Half Day (First)"), ("second_half", "Half Day (Second)")],
)
def test_10_the_detail_response_carries_the_half_while_withdrawing(
    client, login, team, mailer, period, label,
):
    """Requirement 10. The page a reviewer decides the withdrawal on reads the
    detail endpoint, and it must not describe a half day as Normal there either.
    Asserted for the reviewer, who is not the request's author."""
    req_id = _approved_request(client, login, start=HALF_DAY, end=HALF_DAY, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.get(f"{API}/{req_id}", headers=login("hdc-pm@x.com"))

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "cancellation_requested"
    assert body["half_day_period"] == period
    assert leave_type_label(LeaveClassification(body["classification"]),
                            LeaveHalfDayPeriod(body["half_day_period"])) == label


# ---------- 11-12. the reviewer's two decisions ------------------------------

@pytest.mark.parametrize(("start", "end", "period"), LEAVE_SHAPES)
def test_11_an_authorised_reviewer_approves_the_cancellation(
    client, login, db, team, mailer, start, end, period,
):
    """Requirement 11, for every kind of leave. This is the endpoint the detail
    page's Approve cancellation button calls - the same one the queue's row
    calls, under the same authorisation."""
    req_id = _approved_request(client, login, start=start, end=end, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.post(
        f"{API}/{req_id}/approve-cancellation", headers=login("hdc-pm@x.com")
    )

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "cancelled"
    assert db.get(LeaveRequest, req_id).status is LeaveStatus.cancelled


@pytest.mark.parametrize(("start", "end", "period"), LEAVE_SHAPES)
def test_12_an_authorised_reviewer_rejects_the_cancellation(
    client, login, db, team, mailer, start, end, period,
):
    """Requirement 12. Rejecting a withdrawal leaves the leave exactly as
    approved - it does not cancel, and it does not re-open for review."""
    req_id = _approved_request(client, login, start=start, end=end, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.post(
        f"{API}/{req_id}/reject-cancellation", headers=login("hdc-pm@x.com")
    )

    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert db.get(LeaveRequest, req_id).status is LeaveStatus.approved


# ---------- 13. and nobody else -----------------------------------------------

@pytest.mark.parametrize("decision", ["approve-cancellation", "reject-cancellation"])
@pytest.mark.parametrize("period", [None, "first_half", "second_half"])
def test_13_the_author_cannot_decide_their_own_withdrawal(
    client, login, db, team, mailer, decision, period,
):
    """Requirement 13. The detail page hides the card; THIS is what refuses it.

    Offering the decision on the request's own page is exactly why this matters:
    the author is a reader of that page.
    """
    start = HALF_DAY if period else NORMAL_DAY
    req_id = _approved_request(client, login, start=start, end=start, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.post(f"{API}/{req_id}/{decision}", headers=login("hdc-emp@x.com"))

    assert res.status_code == 403, res.text
    assert db.get(LeaveRequest, req_id).status is LeaveStatus.cancellation_requested


@pytest.mark.parametrize("decision", ["approve-cancellation", "reject-cancellation"])
@pytest.mark.parametrize("period", [None, "first_half", "second_half"])
def test_13b_an_unrelated_employee_cannot_decide_a_withdrawal(
    client, login, db, team, mailer, decision, period,
):
    """Signed in, has an employee record, is neither a PM nor the routed
    project's Head - and is refused on both decision endpoints."""
    start = HALF_DAY if period else NORMAL_DAY
    req_id = _approved_request(client, login, start=start, end=start, period=period)
    assert _ask_to_withdraw(client, login, req_id).status_code == 200

    res = client.post(f"{API}/{req_id}/{decision}", headers=login("hdc-other@x.com"))

    assert res.status_code == 403, res.text
    assert db.get(LeaveRequest, req_id).status is LeaveStatus.cancellation_requested


@pytest.mark.parametrize("period", [None, "first_half", "second_half"])
def test_13c_only_the_author_may_ask_for_the_cancellation(
    client, login, db, team, mailer, period,
):
    """The other half of the same rule: asking is the author's act, and a half
    day is asked for by exactly the same person a full day is."""
    start = HALF_DAY if period else NORMAL_DAY
    req_id = _approved_request(client, login, start=start, end=start, period=period)

    res = _ask_to_withdraw(client, login, req_id, email="hdc-other@x.com")

    assert res.status_code == 403, res.text
    assert db.get(LeaveRequest, req_id).status is LeaveStatus.approved


# ---------- 16-17. the full-day workflow did not move ------------------------

def test_16_full_day_cancellation_is_unchanged(client, login, db, team, mailer):
    """Requirement 16. A full-day request reports no half at any step, so every
    surface reads it exactly as it did before half days existed."""
    req_id = _approved_request(client, login, start=NORMAL_DAY, end=NORMAL_DAY)

    asked = _ask_to_withdraw(client, login, req_id)
    assert asked.status_code == 200, asked.text
    assert asked.json()["half_day_period"] is None
    assert asked.json()["classification"] == "normal"

    decided = client.post(
        f"{API}/{req_id}/approve-cancellation", headers=login("hdc-pm@x.com")
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["status"] == "cancelled"
    assert decided.json()["half_day_period"] is None
    assert db.get(LeaveRequest, req_id).half_day_period is None


def test_17_normal_and_special_still_classify_as_they_did(
    client, login, team, mailer,
):
    """Requirement 17. Withdrawing a request does not restate its type: Normal and
    Special remain the backend's own derivation from the working days, and a
    request with no half is described by that derivation alone."""
    normal_id = _approved_request(client, login, start=NORMAL_DAY, end=NORMAL_DAY)
    special_id = _approved_request(client, login, start=SPECIAL_START, end=SPECIAL_END)

    normal = _ask_to_withdraw(client, login, normal_id).json()
    special = _ask_to_withdraw(client, login, special_id).json()

    assert normal["classification"] == "normal"
    assert normal["working_days"] <= 3
    assert leave_type_label(LeaveClassification.normal, None) == "Normal Leave"
    assert special["classification"] == "special"
    assert special["working_days"] > 3
    assert leave_type_label(LeaveClassification.special, None) == "Special Leave"


def test_16b_the_cancellation_decisions_still_send_no_email(
    client, login, team, mailer,
):
    """Cancellation stays in-app. The withdrawal, and both decisions on it, add
    nothing to the mail queue - only the submission and the approval did, and
    that is unchanged by making the decision available on the detail page."""
    req_id = _approved_request(client, login, start=HALF_DAY, end=HALF_DAY,
                               period="first_half")
    # [0] submission to the PM, [1] approval to the employee.
    assert len(mailer.calls) == 2

    assert _ask_to_withdraw(client, login, req_id).status_code == 200
    assert client.post(
        f"{API}/{req_id}/approve-cancellation", headers=login("hdc-pm@x.com")
    ).status_code == 200

    assert len(mailer.calls) == 2
