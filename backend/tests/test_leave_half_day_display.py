"""Phase 2 correction: a half-day request is DISPLAYED and EMAILED as one.

THE BUG THIS PINS DOWN
======================
Phase 2 stored `half_day_period` on the row and put it on every response, and
then nothing read it back. Every place that names a request's Type composed that
name from the derived Normal/Special `classification` alone - and a half-day
request classifies NORMAL, because it covers one working day and one is <= 3.

So a half day filed for 04 Sep 2026 was reported as:

    Email subject/body   Normal Leave
    Leave detail         Leave Type: Normal, Duration: 1 day
    Pending queue        Normal
    Own request list     Normal

The value was persisted correctly the whole time; the propagation stopped at the
last step, where somebody has to decide what to SHOW. `models.leave_type_label`
and `models.leave_duration_label` are that decision, made once, and the emails
and (through their frontend mirrors) all three tables go through them.

WHAT IS DELIBERATELY UNCHANGED, AND ASSERTED HERE
=================================================
Normal and Special, routing, the in-app notification, the overlap rule and the
single-date rule. Half-day leave adds a more specific NAME for a request; it is
not a second kind of request and nothing about the existing ones moves.

STILL OUT OF SCOPE (Phase 3): no `half_day` attendance row, no
`leave_day_fraction`, no balance movement, and the Attendance Day Ledger is not
touched. The numbering below follows the correction brief's own list.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_display.py
"""
from datetime import date, timedelta

import pytest

from app.modules.leave import email as leave_email
from app.modules.leave import routing
from app.modules.leave.classification import LeaveClassification
from app.modules.leave.models import (
    HALF_DAY_DURATION_LABEL,
    LeaveHalfDayPeriod,
    LeaveRequest,
    leave_duration_label,
    leave_type_label,
)
from app.modules.notifications.models import Notification
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

API = "/api/v1/leave-requests"
ALL_REQUESTS = "/api/v1/all-requests"

# A working Wednesday far enough out that no real calendar collides with it.
DAY = date(2027, 3, 3)
# A fortnight - more than 3 working days on any office calendar, so Special.
LONG_START = date(2027, 4, 5)
LONG_END = LONG_START + timedelta(days=13)


class _Recorder:
    """Stands in for `enqueue_email`, capturing what would have been queued."""

    def __init__(self):
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return EnqueueResult(queued=True, task_id="task-1", recipients=())

    @property
    def recipients(self) -> list:
        return [c["to"] for c in self.calls]


@pytest.fixture()
def mailer(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(leave_email, "enqueue_email", rec)
    return rec


@pytest.fixture()
def team(make_user, make_employee):
    """A requester with a reporting PM - the fallback rung of the leave
    recipient chain, and therefore the shape a request takes when no Project
    Head is resolved. The PM needs a login (the bell) and a `work_email` (the
    inbox); the employee needs a `work_email` to receive a decision email."""
    pm_user = make_user("hdd-pm@x.com", role=UserRole.project_manager)
    pm = make_employee(
        employee_code="HDDPM", first_name="Priya", last_name="M",
        user_id=pm_user.id, work_email="priya.m@cdccmms.com",
    )
    emp_user = make_user("hdd-emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="HDDEMP", first_name="Sowrish Kumar", last_name="S",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
        work_email="sowrish.s@cdccmms.com",
    )
    return {"pm_user": pm_user, "pm": pm, "employee": emp}


def _post(client, headers, **overrides):
    body = {
        "start_date": DAY.isoformat(),
        "end_date": DAY.isoformat(),
        "reason": "Personal",
    }
    body.update(overrides)
    return client.post(API, headers=headers, json=body)


def _detail_lines(call: dict) -> list[str]:
    return call["text_body"].splitlines()


# ======================================================================
# 1-2. The employee's choice of half is persisted
# ======================================================================

def test_1_half_day_first_persists_first_half(client, login, db, team, mailer):
    res = _post(client, login("hdd-emp@x.com"), half_day_period="first_half")

    assert res.status_code == 201, res.text
    row = db.get(LeaveRequest, res.json()["id"])
    assert row.half_day_period is LeaveHalfDayPeriod.first_half
    assert row.start_date == row.end_date == DAY


def test_2_half_day_second_persists_second_half(client, login, db, team, mailer):
    res = _post(client, login("hdd-emp@x.com"), half_day_period="second_half")

    assert res.status_code == 201, res.text
    row = db.get(LeaveRequest, res.json()["id"])
    assert row.half_day_period is LeaveHalfDayPeriod.second_half


# ======================================================================
# 3. The API returns the half on every response shape
# ======================================================================

@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_3_the_api_returns_the_half_everywhere(client, login, team, mailer, period):
    """Create -> detail -> list -> All Requests. Whatever a screen reads its
    rows from, the half is on them - which is the whole precondition for
    displaying it."""
    headers = login("hdd-emp@x.com")
    created = _post(client, headers, half_day_period=period)
    assert created.status_code == 201, created.text
    assert created.json()["half_day_period"] == period
    req_id = created.json()["id"]

    detail = client.get(f"{API}/{req_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["half_day_period"] == period

    listing = client.get(API, headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["half_day_period"] == period

    everything = client.get(ALL_REQUESTS, headers=headers)
    assert everything.status_code == 200, everything.text
    row = next(r for r in everything.json()["items"] if r["id"] == req_id)
    assert row["half_day_period"] == period


def test_3b_a_full_day_request_reports_no_half_anywhere(client, login, team, mailer):
    """The absence of a half is what makes a request full-day, so it has to be
    reported as absent rather than as anything."""
    headers = login("hdd-emp@x.com")
    created = _post(client, headers)
    assert created.status_code == 201, created.text

    assert created.json()["half_day_period"] is None
    detail = client.get(f"{API}/{created.json()['id']}", headers=headers)
    assert detail.json()["half_day_period"] is None
    everything = client.get(ALL_REQUESTS, headers=headers)
    assert everything.json()["items"][0]["half_day_period"] is None


def test_3c_a_permission_row_carries_no_half_day_period(
    client, login, db, team, mailer, make_permission_request,
):
    """The All Requests union puts both kinds in one shape. A permission's own
    `period` is which half of the day it covers IN HOURS - a different fact, and
    it must not be smuggled into the leave column."""
    make_permission_request(employee_id=team["employee"].id, permission_date=DAY)

    everything = client.get(ALL_REQUESTS, headers=login("hdd-emp@x.com"))
    assert everything.status_code == 200, everything.text
    perms = [r for r in everything.json()["items"] if r["kind"] == "permission"]
    assert perms, everything.text
    assert all(r["half_day_period"] is None for r in perms)


# ======================================================================
# 4-6. What the detail page, the pending queue and the own-request list show
# ======================================================================
#
# The three surfaces render through one composer, so the precedence is asserted
# once on that composer and the endpoints above prove the fact reaches each of
# them. The frontend mirror is pinned in
# `frontend/src/features/leave/types.half-day-display.test.ts`.

def test_4_5_6_the_half_is_the_displayed_type(client, login, team, mailer):
    """Leave detail, the pending/team queue and the employee's own list all name
    the request by this composer, and it names the half."""
    assert leave_type_label(LeaveClassification.normal, LeaveHalfDayPeriod.first_half) == (
        "Half Day (First)"
    )
    assert leave_type_label(LeaveClassification.normal, LeaveHalfDayPeriod.second_half) == (
        "Half Day (Second)"
    )


def test_4b_the_half_beats_the_classification_the_request_also_carries(
    client, login, team, mailer,
):
    """THE CENTRAL ASSERTION OF THIS CORRECTION.

    A half-day request is classified Normal - one working day is <= 3 - and that
    classification is still on the response. Displaying it INSTEAD OF the half is
    the reported bug, so the two are asserted together: the request classifies
    normal, and is displayed as a half day.
    """
    res = _post(client, login("hdd-emp@x.com"), half_day_period="first_half")
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["classification"] == "normal"
    assert body["half_day_period"] == "first_half"
    assert leave_type_label(
        LeaveClassification(body["classification"]),
        LeaveHalfDayPeriod(body["half_day_period"]),
    ) == "Half Day (First)"


def test_4c_a_half_day_is_never_displayed_as_normal():
    for period in LeaveHalfDayPeriod:
        for classification in LeaveClassification:
            label = leave_type_label(classification, period)
            assert label not in ("Normal", "Normal Leave"), label
            assert label not in ("Special", "Special Leave"), label


# ======================================================================
# 7. Duration
# ======================================================================

def test_7_a_half_day_duration_is_half_a_day():
    assert leave_duration_label(1, LeaveHalfDayPeriod.first_half) == "0.5 day"
    assert leave_duration_label(1, LeaveHalfDayPeriod.second_half) == "0.5 day"
    assert HALF_DAY_DURATION_LABEL == "0.5 day"


def test_7b_a_half_day_never_reports_the_one_working_day_it_covers():
    """The count is honestly 1 - the day IS a working day - which is exactly why
    the raw count could not be left on the Duration line."""
    assert leave_duration_label(1, LeaveHalfDayPeriod.first_half) != "1 day"


def test_7c_the_half_day_duration_is_singular():
    assert not HALF_DAY_DURATION_LABEL.endswith("days")


def test_7d_a_full_day_duration_is_the_working_day_count(client, login, team, mailer):
    assert leave_duration_label(1, None) == "1 day"
    assert leave_duration_label(3, None) == "3 days"
    assert leave_duration_label(0, None) == "0 days"


# ======================================================================
# 8-9. The email recognises both halves
# ======================================================================

@pytest.mark.parametrize(
    ("period", "label"),
    [("first_half", "Half Day (First)"), ("second_half", "Half Day (Second)")],
)
def test_8_9_the_submission_email_names_the_half(
    client, login, team, mailer, period, label,
):
    """Subject, Leave Type and Leave Period, through the real send path.

    The period NAMES the absence - "(Half day)" - rather than pricing it. That
    wording is `email._HALF_DAY_PERIOD_DURATION` and is deliberately not the
    "0.5 day" of `HALF_DAY_DURATION_LABEL`, which the in-app Duration row still
    reads; see `test_7_a_half_day_duration_is_half_a_day` above, which pins that
    one down and is unchanged.
    """
    res = _post(client, login("hdd-emp@x.com"), half_day_period=period)
    assert res.status_code == 201, res.text

    assert len(mailer.calls) == 1
    call = mailer.calls[0]
    assert call["subject"] == (
        "Half Day Leave Request - Sowrish Kumar S - Action Required"
    )
    lines = _detail_lines(call)
    assert f"Leave Type: {label}" in lines
    assert "Leave Period: 03 Mar 2027 (Half day)" in lines
    # The letter never states the fraction, in either part of the message.
    assert HALF_DAY_DURATION_LABEL not in call["text_body"]
    assert HALF_DAY_DURATION_LABEL not in call["html_body"]


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_8_9b_the_submission_email_never_says_normal_for_a_half_day(
    client, login, team, mailer, period,
):
    """The exact symptom that was reported from the inbox."""
    assert _post(
        client, login("hdd-emp@x.com"), half_day_period=period
    ).status_code == 201

    call = mailer.calls[0]
    assert "Normal Leave" not in call["text_body"]
    assert "Normal Leave" not in call["html_body"]
    assert "(1 day)" not in call["text_body"]


@pytest.mark.parametrize(
    ("period", "label"),
    [("first_half", "Half Day (First)"), ("second_half", "Half Day (Second)")],
)
def test_8_9c_the_decision_email_names_the_half(
    client, login, team, mailer, period, label,
):
    """The employee is told the outcome of the request they FILED, so it has to
    be described as the request they filed. Approval and rejection both."""
    created = _post(client, login("hdd-emp@x.com"), half_day_period=period)
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    decided = client.post(
        f"{API}/{req_id}/reject", headers=login("hdd-pm@x.com"), json={}
    )
    assert decided.status_code == 200, decided.text

    # [0] is the submission email to the PM; [1] is the decision to the employee.
    assert len(mailer.calls) == 2
    call = mailer.calls[1]
    assert call["to"] == "sowrish.s@cdccmms.com"
    assert call["subject"] == "Half Day Leave Request - Rejected"
    lines = _detail_lines(call)
    assert f"Leave Type: {label}" in lines
    # Same period wording as the submission email - one renderer, one rule.
    assert "Leave Period: 03 Mar 2027 (Half day)" in lines


def test_8_9d_the_subject_distinguishes_a_half_day_at_a_glance(
    client, login, team, mailer,
):
    """A reader scanning subject lines must be able to tell the two apart
    without opening either."""
    res = _post(client, login("hdd-emp@x.com"), half_day_period="first_half")
    assert res.status_code == 201, res.text

    subject = mailer.calls[0]["subject"]
    assert subject.startswith("Half Day Leave Request - ")
    assert subject != "Leave Request - Sowrish Kumar S - Action Required"


def test_8_9e_the_pure_renderers_default_to_a_full_day(client, login, team):
    """`half_day_period` is optional on both renderers and defaults to None, so
    every existing caller renders byte for byte the email it always did."""
    submission = leave_email.render_submission_email(
        recipient_name="Priya M",
        employee_name="Sowrish Kumar S",
        classification=LeaveClassification.normal,
        start_date=DAY,
        end_date=DAY,
        working_days=1,
        reason=None,
        request_id="r-1",
        link=None,
    )
    assert submission.subject == (
        "Leave Request - Sowrish Kumar S - Action Required"
    )
    assert "Leave Type: Normal Leave" in submission.text_body

    decision = leave_email.render_decision_email(
        approved=True,
        employee_name="Sowrish Kumar S",
        reviewer_name="Priya M",
        classification=LeaveClassification.normal,
        start_date=DAY,
        end_date=DAY,
        working_days=1,
        reason=None,
        reviewer_comment=None,
        request_id="r-1",
        link=None,
    )
    assert decision.subject == "Leave Request - Approved"


# ======================================================================
# 10-11. Normal and Special are untouched
# ======================================================================

def test_10_a_normal_request_still_displays_normal(client, login, team, mailer):
    res = _post(client, login("hdd-emp@x.com"))
    assert res.status_code == 201, res.text

    assert res.json()["classification"] == "normal"
    assert res.json()["half_day_period"] is None
    assert leave_type_label(LeaveClassification.normal, None) == "Normal Leave"
    assert "Leave Type: Normal Leave" in _detail_lines(mailer.calls[0])


def test_11_a_special_request_still_displays_special(client, login, team, mailer):
    res = _post(
        client, login("hdd-emp@x.com"),
        start_date=LONG_START.isoformat(), end_date=LONG_END.isoformat(),
    )
    assert res.status_code == 201, res.text

    assert res.json()["working_days"] > 3
    assert res.json()["classification"] == "special"
    assert leave_type_label(LeaveClassification.special, None) == "Special Leave"
    assert "Leave Type: Special Leave" in _detail_lines(mailer.calls[0])


def test_11b_the_full_day_subject_and_period_are_byte_for_byte_unchanged(
    client, login, team, mailer,
):
    """The existing wording is not restyled while a new case is added to it."""
    assert _post(client, login("hdd-emp@x.com")).status_code == 201

    call = mailer.calls[0]
    assert call["subject"] == "Leave Request - Sowrish Kumar S - Action Required"
    assert "Leave Period: 03 Mar 2027 (1 day)" in _detail_lines(call)


# ======================================================================
# 12-13. Routing and the in-app notification are unchanged
# ======================================================================

def test_12_routing_is_unchanged_for_a_half_day(client, login, db, team, mailer):
    """`routing.resolve_routed_project` is asked the same question from the same
    start date, and its answer is stored verbatim."""
    res = _post(client, login("hdd-emp@x.com"), half_day_period="first_half")
    assert res.status_code == 201, res.text

    expected = routing.resolve_routed_project(db, team["employee"].id, DAY)
    assert db.get(LeaveRequest, res.json()["id"]).routed_project_id == expected


def test_12b_the_same_one_approver_is_reached(client, login, db, team, mailer):
    """One bell and one email, to the person the request was routed to - the
    same `_notify_routed_approver` / `send_submission_email` pair the full-day
    path uses."""
    res = _post(client, login("hdd-emp@x.com"), half_day_period="second_half")
    assert res.status_code == 201, res.text

    notes = db.query(Notification).all()
    assert len(notes) == 1
    assert notes[0].user_id == team["pm_user"].id
    assert notes[0].type == "leave_submitted"
    assert mailer.recipients == ["priya.m@cdccmms.com"]


def test_13_the_in_app_notification_wording_is_unchanged(
    client, login, db, team, mailer, make_user, make_employee,
):
    """DELIBERATE, AND NOT AN OVERSIGHT. The correction brief changes the EMAIL,
    which is where the reader saw "Normal Leave". The bell's message is composed
    from the classification and is explicitly left alone, so a half-day
    submission still rings exactly as a full-day one of the same length does.
    """
    other_user = make_user("hdd-emp2@x.com", role=UserRole.employee)
    make_employee(
        employee_code="HDDEMP2", first_name="Sowrish Kumar", last_name="S",
        user_id=other_user.id, reporting_pm_id=team["pm_user"].id,
    )

    _post(client, login("hdd-emp@x.com"))
    _post(client, login("hdd-emp2@x.com"), half_day_period="first_half")

    messages = [n.message for n in db.query(Notification).all()]
    assert len(messages) == 2
    assert messages[0] == messages[1]


# ======================================================================
# 14. A half day is half of ONE day
# ======================================================================

@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_14_a_multi_day_half_day_is_rejected(client, login, db, team, mailer, period):
    res = _post(
        client, login("hdd-emp@x.com"),
        start_date=DAY.isoformat(),
        end_date=(DAY + timedelta(days=1)).isoformat(),
        half_day_period=period,
    )

    assert res.status_code == 422, res.text
    assert "one day" in res.text
    # The refusal is total: no partial row and no email.
    assert db.query(LeaveRequest).count() == 0
    assert mailer.calls == []


def test_14b_multi_day_full_day_leave_is_still_accepted(client, login, team, mailer):
    """The single-date rule is a HALF-DAY rule and nothing else."""
    res = _post(
        client, login("hdd-emp@x.com"),
        start_date=LONG_START.isoformat(), end_date=LONG_END.isoformat(),
    )

    assert res.status_code == 201, res.text
    assert res.json()["start_date"] != res.json()["end_date"]


# ======================================================================
# 15. Overlap is unchanged
# ======================================================================

def test_15_two_live_requests_on_one_date_are_still_refused(
    client, login, team, mailer,
):
    headers = login("hdd-emp@x.com")
    assert _post(client, headers).status_code == 201

    assert _post(client, headers).status_code == 422


def test_15b_the_two_halves_of_one_day_still_clash(client, login, team, mailer):
    """FOR NOW, AND ON PURPOSE. The two halves do not overlap in real life, but
    the overlap rule works on DATES and this correction does not change it."""
    headers = login("hdd-emp@x.com")
    assert _post(client, headers, half_day_period="first_half").status_code == 201

    assert _post(client, headers, half_day_period="second_half").status_code == 422


def test_15c_a_half_day_on_a_free_date_is_not_blocked(client, login, team, mailer):
    headers = login("hdd-emp@x.com")
    assert _post(client, headers, half_day_period="first_half").status_code == 201

    later = _post(
        client, headers,
        start_date=(DAY + timedelta(days=7)).isoformat(),
        end_date=(DAY + timedelta(days=7)).isoformat(),
        half_day_period="second_half",
    )

    assert later.status_code == 201, later.text
