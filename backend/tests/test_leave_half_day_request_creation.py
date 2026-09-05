"""Phase 2 of half-day leave: the employee's choice of half survives creation.

WHAT THIS PHASE ADDS
====================
Phase 1 gave `leave_requests` a `half_day_period` column and taught
`LeaveRequestCreate` to validate it, but `create_leave_request` dropped the
value on the floor. Phase 2 adds the ONE line that stores it, and the Leave
Request dialog that lets an employee pick it.

So the burden of proof here is almost entirely NEGATIVE. Storing a half must
change nothing else about filing leave, and most of this file exists to say so
out loud:

  * Normal and Special still work, and are still DERIVED from the dates - the
    dropdown's Normal/Special entries are the shape of the form, never a
    classification the employee gets to assert;
  * the same overlap rule refuses the same requests, half days included;
  * the same `routing.resolve_routed_project` resolves the same project;
  * the same one person is notified and emailed, through the same chain;
  * a full-day request and a half-day request filed under identical conditions
    differ in `half_day_period` AND NOTHING ELSE - asserted column by column, so
    a future special case cannot be added quietly.

STILL OUT OF SCOPE (Phase 3): no approval writes a `half_day` attendance row, no
`leave_day_fraction` is set and no balance moves. The test at the bottom pins
that boundary.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_request_creation.py
"""
from datetime import date, timedelta

import pytest

from app.modules.leave import email as leave_email
from app.modules.leave import routing
from app.modules.leave.models import LeaveHalfDayPeriod, LeaveRequest, LeaveStatus
from app.modules.notifications.models import Notification
from app.modules.users.models import UserRole
from app.notifications.email_dispatch import EnqueueResult

API = "/api/v1/leave-requests"

# Far enough out that nothing collides with the real "today", and far enough
# apart that the two ranges below never overlap each other.
DAY = date.today() + timedelta(days=30)
LONG_START = date.today() + timedelta(days=60)
LONG_END = LONG_START + timedelta(days=13)  # two calendar weeks - always > 3
                                            # working days on any office calendar


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
    recipient chain, and the shape a request takes when no Project Head is
    resolved. The PM needs both a login (the bell's target) and an employee row
    carrying a `work_email` (the email's target)."""
    pm_user = make_user("h2-pm@x.com", role=UserRole.project_manager)
    make_employee(
        employee_code="H2PM", first_name="Priya", last_name="M",
        user_id=pm_user.id, work_email="priya.m@cdccmms.com",
    )
    emp_user = make_user("h2-emp@x.com", role=UserRole.employee)
    emp = make_employee(
        employee_code="H2EMP", first_name="Arun", last_name="K",
        user_id=emp_user.id, reporting_pm_id=pm_user.id,
    )
    return {"pm_user": pm_user, "employee": emp}


def _post(client, headers, **overrides):
    body = {
        "start_date": DAY.isoformat(),
        "end_date": DAY.isoformat(),
        "reason": "Personal",
    }
    body.update(overrides)
    return client.post(API, headers=headers, json=body)


def _row(db, request_id) -> LeaveRequest:
    return db.get(LeaveRequest, request_id)


# ======================================================================
# 1-2. Normal and Special still work, and are still derived
# ======================================================================

def test_a_normal_request_is_filed_exactly_as_before(client, login, team, mailer):
    """A single working day: <= 3 working days, so Normal. No half named, so a
    full-day leave - which is every request CoreOps had before Phase 2."""
    res = _post(client, login("h2-emp@x.com"))

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["classification"] == "normal"
    assert body["half_day_period"] is None
    assert body["status"] == "pending"
    assert body["start_date"] == DAY.isoformat()
    assert body["end_date"] == DAY.isoformat()


def test_a_special_request_is_filed_exactly_as_before(client, login, team, mailer):
    """A fortnight costs more than 3 working days on any office calendar, so
    Special. Still DERIVED from the dates - nothing in the payload says so."""
    res = _post(
        client, login("h2-emp@x.com"),
        start_date=LONG_START.isoformat(), end_date=LONG_END.isoformat(),
    )

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["working_days"] > 3
    assert body["classification"] == "special"
    assert body["half_day_period"] is None


def test_the_classification_is_never_taken_from_the_payload(client, login, team, mailer):
    """THE DROPDOWN IS NOT AN OVERRIDE. Normal/Special are the form's two
    full-day shapes; the backend still decides which one a request IS, from the
    working days its dates cost. A body that tries to assert otherwise is
    ignored, not honoured - so the dialog cannot promise a classification the
    saved request disagrees with."""
    res = _post(
        client, login("h2-emp@x.com"),
        start_date=LONG_START.isoformat(), end_date=LONG_END.isoformat(),
        classification="normal", leave_type="normal",
    )

    assert res.status_code == 201, res.text
    assert res.json()["classification"] == "special"


# ======================================================================
# 3-5. Both halves can be created, and both persist
# ======================================================================

@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("first_half", LeaveHalfDayPeriod.first_half),
        ("second_half", LeaveHalfDayPeriod.second_half),
    ],
)
def test_a_half_day_is_created_for_one_date(
    client, login, db, team, mailer, period, expected,
):
    """Half Day (First) and Half Day (Second), each for exactly one date."""
    res = _post(client, login("h2-emp@x.com"), half_day_period=period)

    assert res.status_code == 201, res.text
    body = res.json()
    assert body["half_day_period"] == period
    assert body["start_date"] == body["end_date"] == DAY.isoformat()

    # And on the row itself, not just in the response.
    row = _row(db, body["id"])
    assert row.half_day_period is expected
    assert row.start_date == row.end_date == DAY


def test_the_half_survives_a_read_back_through_every_endpoint(
    client, login, team, mailer,
):
    """Create -> detail -> list. The value is on the stored row, so every
    response shape carries it, including the one the mutation returns straight
    into the client's cache."""
    headers = login("h2-emp@x.com")
    created = _post(client, headers, half_day_period="second_half")
    assert created.status_code == 201, created.text
    req_id = created.json()["id"]

    detail = client.get(f"{API}/{req_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["half_day_period"] == "second_half"

    listing = client.get(API, headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["half_day_period"] == "second_half"


def test_a_half_day_is_one_working_day_and_therefore_normal(client, login, team, mailer):
    """The classification rule is untouched: one working day is <= 3, so a
    half-day request classifies Normal. What it COSTS is Phase 3's business -
    nothing here prices it."""
    res = _post(client, login("h2-emp@x.com"), half_day_period="first_half")

    assert res.status_code == 201, res.text
    assert res.json()["working_days"] == 1
    assert res.json()["classification"] == "normal"


# ======================================================================
# 6. A half day cannot span more than one date
# ======================================================================

def test_a_multi_date_half_day_is_rejected(client, login, team, mailer):
    """Refused by the schema, so the API answers 422 before any row is read -
    and the dialog never offers the shape in the first place, because picking a
    half swaps the From/To pair for a single Date field."""
    res = _post(
        client, login("h2-emp@x.com"),
        start_date=DAY.isoformat(),
        end_date=(DAY + timedelta(days=1)).isoformat(),
        half_day_period="first_half",
    )

    assert res.status_code == 422, res.text
    assert "one day" in res.text


def test_a_multi_date_half_day_stores_nothing(client, login, db, team, mailer):
    """The refusal is total: no partial row, and no email either."""
    _post(
        client, login("h2-emp@x.com"),
        start_date=DAY.isoformat(),
        end_date=(DAY + timedelta(days=1)).isoformat(),
        half_day_period="second_half",
    )

    assert db.query(LeaveRequest).count() == 0
    assert mailer.calls == []


def test_a_full_day_request_keeps_every_range_it_has_always_accepted(
    client, login, team, mailer,
):
    """The single-date rule is a HALF-DAY rule and nothing else. Multi-day leave
    is exactly as multi-day as it was."""
    res = _post(
        client, login("h2-emp@x.com"),
        start_date=LONG_START.isoformat(), end_date=LONG_END.isoformat(),
    )

    assert res.status_code == 201, res.text
    assert res.json()["start_date"] != res.json()["end_date"]


# ======================================================================
# 7. Everything else about creation is unchanged
# ======================================================================

def test_a_half_day_row_differs_from_a_full_day_row_in_exactly_one_column(
    client, login, db, make_user, make_employee, team, mailer,
):
    """THE CENTRAL ASSERTION OF THIS PHASE, column by column.

    Two employees with identical setups file on the same date, one full-day and
    one half-day. Every stored value must match except `half_day_period` - so if
    anybody ever special-cases half days in `create_leave_request`, this fails
    and names the column they touched.

    Two employees rather than one because the overlap rule (correctly, and still)
    refuses a second live request on a date the first already covers.
    """
    other_user = make_user("h2-emp2@x.com", role=UserRole.employee)
    make_employee(
        employee_code="H2EMP2", first_name="Arun", last_name="K",
        user_id=other_user.id, reporting_pm_id=team["pm_user"].id,
    )

    full = _post(client, login("h2-emp@x.com"))
    half = _post(client, login("h2-emp2@x.com"), half_day_period="first_half")
    assert full.status_code == 201, full.text
    assert half.status_code == 201, half.text

    full_row = _row(db, full.json()["id"])
    half_row = _row(db, half.json()["id"])

    # Identity and ownership differ by construction; everything else is the
    # comparison. `created_by`/`updated_by` are the two logins, likewise.
    skip = {"id", "employee_id", "created_by", "updated_by", "created_at", "updated_at"}
    compared = [
        c.key for c in LeaveRequest.__table__.columns if c.key not in skip
    ]
    assert "half_day_period" in compared, "the one column under test must be compared"

    differences = {
        key
        for key in compared
        if getattr(full_row, key) != getattr(half_row, key)
    }
    assert differences == {"half_day_period"}, differences


def test_the_existing_create_body_still_works_untouched(client, login, team, mailer):
    """No new REQUIRED field. The exact three keys the leave form has always
    sent are still a complete request."""
    res = client.post(
        API,
        headers=login("h2-emp@x.com"),
        json={
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "reason": "Family function",
        },
    )

    assert res.status_code == 201, res.text
    assert res.json()["half_day_period"] is None
    assert res.json()["reason"] == "Family function"


def test_an_incomplete_half_day_request_is_still_refused(client, login, team, mailer):
    """Declaring half a day without naming which half is not a request. Phase 1's
    rule, still live through the whole creation path."""
    res = _post(client, login("h2-emp@x.com"), half_day=True)

    assert res.status_code == 422, res.text


def test_a_half_day_request_still_needs_an_employee_profile(client, login, make_user):
    """The very first check `create_leave_request` makes, unchanged. A half day
    does not get a shortcut past it."""
    make_user("h2-noprofile@x.com", role=UserRole.employee)

    res = _post(client, login("h2-noprofile@x.com"), half_day_period="first_half")

    assert res.status_code == 422, res.text
    assert "employee profile" in res.text


# ======================================================================
# 8. Routing is unchanged
# ======================================================================

def test_a_half_day_routes_through_the_same_resolver(client, login, db, team, mailer):
    """`routing.resolve_routed_project` is asked the same question, from the same
    start date, and its answer is stored verbatim. Nothing about a half day
    changes which project a request belongs to."""
    res = _post(client, login("h2-emp@x.com"), half_day_period="second_half")
    assert res.status_code == 201, res.text

    expected = routing.resolve_routed_project(db, team["employee"].id, DAY)
    assert _row(db, res.json()["id"]).routed_project_id == expected


def test_the_routed_to_line_is_populated_for_a_half_day(client, login, team, mailer):
    """The detail page's "Routed to" resolves through the same chain that
    delivers the submission notification. With no Project Head resolved, that is
    the requester's reporting PM - exactly as for a full-day request."""
    headers = login("h2-emp@x.com")
    created = _post(client, headers, half_day_period="first_half")
    assert created.status_code == 201, created.text

    detail = client.get(f"{API}/{created.json()['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["routed_to_name"] == "Priya M"


# ======================================================================
# 9. Notification and email are unchanged
# ======================================================================

def test_a_half_day_notifies_exactly_the_same_one_approver(
    client, login, db, team, mailer,
):
    """One bell, to the person the request was routed to, with the leave
    submission type and a deep link to the request. Same `_notify_routed_approver`
    call the full-day path makes."""
    res = _post(client, login("h2-emp@x.com"), half_day_period="first_half")
    assert res.status_code == 201, res.text

    notes = db.query(Notification).all()
    assert len(notes) == 1
    note = notes[0]
    assert note.user_id == team["pm_user"].id
    assert note.type == "leave_submitted"
    assert note.entity_type == "leave_request"
    assert str(note.entity_id) == res.json()["id"]


def test_a_half_day_emails_exactly_the_same_one_approver(client, login, team, mailer):
    """One email, to the same recipient the bell reached, through the same
    `send_submission_email`. Submission is still the only leave event that
    emails.

    ROUTING is what is unchanged here, not the WORDING. The subject names the
    half-day kind since the Phase 2 correction, because the approver has to be
    able to tell a half-day request from a full-day one in a list of subject
    lines - see `test_leave_half_day_display.py`. Who it reaches, and that
    exactly one person does, is what this test is about.
    """
    res = _post(client, login("h2-emp@x.com"), half_day_period="second_half")
    assert res.status_code == 201, res.text

    assert mailer.recipients == ["priya.m@cdccmms.com"]
    assert mailer.calls[0]["subject"] == (
        "Half Day Leave Request - Arun K - Action Required"
    )


def test_the_submission_notification_reads_the_same_for_both(
    client, login, db, make_user, make_employee, team, mailer,
):
    """DELIBERATE, AND WORTH STATING. The notification and email wording is
    composed from the Normal/Special classification, and Phase 2 does not touch
    that composition - so a half-day submission reads exactly as a full-day one
    of the same length does. Changing the wording is not in this phase's scope;
    this pins that it was left alone rather than forgotten."""
    other_user = make_user("h2-emp3@x.com", role=UserRole.employee)
    make_employee(
        employee_code="H2EMP3", first_name="Arun", last_name="K",
        user_id=other_user.id, reporting_pm_id=team["pm_user"].id,
    )

    _post(client, login("h2-emp@x.com"))
    _post(client, login("h2-emp3@x.com"), half_day_period="first_half")

    messages = [n.message for n in db.query(Notification).all()]
    assert len(messages) == 2
    assert messages[0] == messages[1]


# ======================================================================
# 10. Overlap is unchanged
# ======================================================================

def test_a_second_live_request_on_the_same_date_is_still_refused(
    client, login, team, mailer,
):
    """The existing rule, untouched."""
    headers = login("h2-emp@x.com")
    assert _post(client, headers).status_code == 201

    second = _post(client, headers)

    assert second.status_code == 422, second.text
    assert "already have a pending leave request" in second.text


def test_two_half_days_on_the_same_date_are_still_refused(client, login, team, mailer):
    """FOR NOW, AND ON PURPOSE. The two halves of one day do not overlap in real
    life, but the overlap rule works on DATES and Phase 2 does not change it -
    so a first-half and a second-half request on the same date still clash.
    Pinned so the limitation is a recorded decision, not a surprise."""
    headers = login("h2-emp@x.com")
    assert _post(client, headers, half_day_period="first_half").status_code == 201

    second = _post(client, headers, half_day_period="second_half")

    assert second.status_code == 422, second.text


def test_a_half_day_still_blocks_a_full_day_on_the_same_date(client, login, team, mailer):
    """And the reverse direction: a half day is a live claim on its date like any
    other, in both directions."""
    headers = login("h2-emp@x.com")
    assert _post(client, headers, half_day_period="first_half").status_code == 201

    assert _post(client, headers).status_code == 422


def test_a_half_day_on_a_free_date_is_not_blocked(client, login, team, mailer):
    """Overlap is still about dates that actually intersect."""
    headers = login("h2-emp@x.com")
    assert _post(client, headers, half_day_period="first_half").status_code == 201

    later = _post(
        client, headers,
        start_date=(DAY + timedelta(days=3)).isoformat(),
        end_date=(DAY + timedelta(days=3)).isoformat(),
        half_day_period="second_half",
    )

    assert later.status_code == 201, later.text


# ======================================================================
# The Phase 2 boundary, stated out loud
# ======================================================================

def test_phase_2_stops_at_the_request(client, login, db, team, mailer):
    """DELIBERATE. The request records which half; nothing yet spends it.

    No attendance row, no `leave_day_fraction`, no balance movement - a half-day
    request is still just a pending request. Phase 3 approves one and writes the
    `half_day` attendance record; this expectation moves then.
    """
    res = _post(client, login("h2-emp@x.com"), half_day_period="first_half")
    assert res.status_code == 201, res.text

    row = _row(db, res.json()["id"])
    assert row.status is LeaveStatus.pending
    assert row.manager_id is None

    from app.modules.attendance.models import AttendanceRecord

    assert db.query(AttendanceRecord).count() == 0
