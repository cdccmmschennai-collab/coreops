"""Phase 1 of half-day leave: the REQUEST can now say which half of a day it is.

WHAT THIS PHASE ADDS, AND WHAT IT DELIBERATELY DOES NOT
=======================================================
Migration 0084 puts `half_day_period` on `leave_requests` and
`LeaveRequestCreate` validates it. That is all. Nothing downstream is wired up
yet - `create_leave_request` does not store the value, no approval writes a
`half_day` attendance row, no ledger figure moves and no screen shows the
variant. Those are later phases, and the test at the very bottom of this file
pins the boundary explicitly so it is a decision rather than an oversight.

So every assertion here is about the DATA MODEL and the SCHEMA:

  * both halves are accepted, and nothing else is;
  * a request that declares itself half a day without naming which half is
    refused, because the two halves are not interchangeable and choosing one for
    the requester would invent a decision;
  * a half day is half of ONE day, at the API and again at the database;
  * a full-day request - which is every request CoreOps has ever had - is
    completely unaffected, and an existing row reads back exactly as before.

    docker exec wms-backend-1 pytest tests/test_leave_half_day_request_model.py
"""
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.modules.leave.models import (
    HALF_DAY_LEAVE_FRACTION,
    HALF_DAY_PERIOD_LABELS,
    LeaveHalfDayPeriod,
    LeaveRequest,
    LeaveStatus,
    LeaveType,
    half_day_period_label,
)
from app.modules.leave.schemas import LeaveRequestCreate, LeaveRequestOut
from app.modules.users.models import UserRole

API = "/api/v1/leave-requests"

# A single working Wednesday, far enough out that no real calendar collides.
DAY = date(2027, 3, 3)
NEXT_DAY = date(2027, 3, 4)


@pytest.fixture()
def team(make_user, make_employee):
    """One PM and one employee - the ordinary shape every leave test uses."""
    mu = make_user("hd-mgr@x.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="HDMGR", user_id=mu.id)
    eu = make_user("hd-emp@x.com", role=UserRole.employee)
    emp = make_employee(employee_code="HDEMP", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp}


def _body(**overrides) -> dict:
    body = {"start_date": DAY, "end_date": DAY, "reason": "Personal"}
    body.update(overrides)
    return body


# ======================================================================
# The two variants are valid
# ======================================================================

def test_first_half_is_a_valid_request(team):
    data = LeaveRequestCreate(**_body(half_day=True, half_day_period="first_half"))
    assert data.half_day_period is LeaveHalfDayPeriod.first_half


def test_second_half_is_a_valid_request(team):
    data = LeaveRequestCreate(**_body(half_day=True, half_day_period="second_half"))
    assert data.half_day_period is LeaveHalfDayPeriod.second_half


def test_naming_a_half_is_enough_on_its_own():
    """The period IS the declaration. A caller that has already chosen a half
    never has to send the `half_day` flag as well - that flag exists only to
    make an INCOMPLETE request refusable, not to gate a complete one."""
    data = LeaveRequestCreate(**_body(half_day_period="second_half"))
    assert data.half_day is False
    assert data.half_day_period is LeaveHalfDayPeriod.second_half


@pytest.mark.parametrize("period", ["first_half", "second_half"])
def test_both_variants_persist_on_the_row(db, team, period):
    req = LeaveRequest(
        employee_id=team["employee"].id,
        leave_type=LeaveType.other,
        start_date=DAY,
        end_date=DAY,
        half_day_period=LeaveHalfDayPeriod(period),
        status=LeaveStatus.pending,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    assert req.half_day_period is LeaveHalfDayPeriod(period)


# ======================================================================
# An incomplete half-day request is refused
# ======================================================================

def test_a_half_day_request_that_names_no_half_is_rejected():
    """"Half a day" is not a request. Which half was taken is the whole point of
    recording one, and neither half may be chosen on the requester's behalf."""
    with pytest.raises(ValidationError) as err:
        LeaveRequestCreate(**_body(half_day=True))
    assert "1st Half or 2nd Half" in str(err.value)


def test_an_explicit_null_half_is_still_incomplete():
    """Sending `half_day_period: null` alongside the flag is the same omission -
    a form that cleared its selection must not slip through as a full day."""
    with pytest.raises(ValidationError):
        LeaveRequestCreate(**_body(half_day=True, half_day_period=None))


@pytest.mark.parametrize(
    "bad",
    ["half_day", "HALF_DAY", "FIRST_HALF", "first", "1st_half", "1", "", "full_day"],
)
def test_only_the_two_halves_exist(bad):
    """There is no third value, and none of the technical spellings a caller
    might guess at is accepted either."""
    with pytest.raises(ValidationError):
        LeaveRequestCreate(**_body(half_day=True, half_day_period=bad))


# ======================================================================
# Half a day is half of ONE day
# ======================================================================

def test_a_half_day_cannot_span_a_range():
    """A range would owe half a day to EACH of its working days, and both
    variants are defined to consume exactly one half day."""
    with pytest.raises(ValidationError) as err:
        LeaveRequestCreate(
            **_body(
                start_date=DAY,
                end_date=NEXT_DAY,
                half_day=True,
                half_day_period="first_half",
            )
        )
    assert "one day" in str(err.value)


def test_the_database_refuses_a_multi_day_half_day_too(db, team):
    """The API validation has a floor under it: a fixture, a script or a future
    endpoint cannot introduce a "half day" spanning a fortnight."""
    db.add(
        LeaveRequest(
            employee_id=team["employee"].id,
            leave_type=LeaveType.other,
            start_date=DAY,
            end_date=NEXT_DAY,
            half_day_period=LeaveHalfDayPeriod.first_half,
            status=LeaveStatus.pending,
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_a_full_day_leave_keeps_every_range_it_has_always_accepted(db, team):
    """The single-day rule is a half-day rule and nothing else."""
    data = LeaveRequestCreate(**_body(start_date=DAY, end_date=NEXT_DAY))
    assert data.half_day_period is None

    req = LeaveRequest(
        employee_id=team["employee"].id,
        leave_type=LeaveType.other,
        start_date=DAY,
        end_date=NEXT_DAY,
        status=LeaveStatus.pending,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    assert req.half_day_period is None


# ======================================================================
# Normal / Special / full-day requests are untouched
# ======================================================================

def test_a_request_that_says_nothing_about_halves_is_a_full_day_request():
    """The default, and therefore what every existing caller sends."""
    data = LeaveRequestCreate(**_body())
    assert data.half_day is False
    assert data.half_day_period is None


def test_the_existing_create_body_still_validates_unchanged():
    """No new REQUIRED field. A body written before migration 0084 - the exact
    three keys the leave form has always sent - is still a valid request."""
    data = LeaveRequestCreate(
        start_date=DAY, end_date=NEXT_DAY, reason="Family function"
    )
    assert (data.start_date, data.end_date) == (DAY, NEXT_DAY)
    assert data.reason == "Family function"


def test_an_existing_row_reads_back_as_a_full_day_leave(db, make_leave_request, team):
    """BACKWARD COMPATIBILITY. Every row already in this table was written
    without the column, and NULL is exactly how the migration leaves it - so a
    historical request is a full-day leave, as it always was, with nothing
    backfilled and no balance moved."""
    req = make_leave_request(
        employee_id=team["employee"].id,
        start_date=DAY,
        end_date=NEXT_DAY,
        status=LeaveStatus.approved,
    )
    db.refresh(req)
    assert req.half_day_period is None


def test_the_existing_api_round_trip_is_unchanged(client, login, team):
    """The whole existing workflow, end to end, with no half-day field in sight:
    create -> list -> detail. Phase 1 must be invisible to it."""
    headers = login("hd-emp@x.com")
    created = client.post(
        API,
        headers=headers,
        json={
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "reason": "Personal",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["classification"] == "normal"
    assert body["half_day_period"] is None

    detail = client.get(f"{API}/{body['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["half_day_period"] is None

    listing = client.get(API, headers=headers)
    assert listing.status_code == 200, listing.text
    assert listing.json()["items"][0]["half_day_period"] is None


def test_the_response_schema_serialises_a_stored_half(db, team):
    """`LeaveRequestOut` carries the variant out to the wire once something
    stores one. Asserted directly on the schema, because the service does not
    store it yet - see the boundary test below."""
    req = LeaveRequest(
        employee_id=team["employee"].id,
        leave_type=LeaveType.other,
        start_date=DAY,
        end_date=DAY,
        half_day_period=LeaveHalfDayPeriod.second_half,
        status=LeaveStatus.pending,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    req.working_days = 1
    req.classification = "normal"

    out = LeaveRequestOut.model_validate(req)
    assert out.half_day_period is LeaveHalfDayPeriod.second_half


# ======================================================================
# The wording, and the quantity
# ======================================================================

def test_each_variant_has_the_exact_user_facing_label():
    assert HALF_DAY_PERIOD_LABELS == {
        LeaveHalfDayPeriod.first_half: "Half Day · 1st Half",
        LeaveHalfDayPeriod.second_half: "Half Day · 2nd Half",
    }


def test_no_technical_name_ever_reaches_a_label():
    """HALF_DAY / FIRST_HALF / SECOND_HALF are storage, not wording."""
    for label in HALF_DAY_PERIOD_LABELS.values():
        assert "HALF_DAY" not in label
        assert "FIRST_HALF" not in label and "SECOND_HALF" not in label
        assert "_" not in label


def test_the_separator_is_a_middle_dot_not_a_dash():
    """The house rule across CoreOps: a plain hyphen or a dot, never an em or en
    dash. Pinned so a copy-paste from a document that autocorrects punctuation
    fails here rather than reaching a screen."""
    for label in HALF_DAY_PERIOD_LABELS.values():
        assert " · " in label, label
        assert "—" not in label and "–" not in label, label


def test_a_full_day_leave_has_no_variant_label():
    """None, not a placeholder: a request with no half is not a half-day leave,
    and its Type is the Normal/Special classification the caller already has."""
    assert half_day_period_label(None) is None
    assert half_day_period_label(LeaveHalfDayPeriod.first_half) == "Half Day · 1st Half"
    assert (
        half_day_period_label(LeaveHalfDayPeriod.second_half) == "Half Day · 2nd Half"
    )


def test_both_variants_are_worth_exactly_one_half_day():
    """One constant, not a per-variant table - which is what makes it impossible
    for a choice of half to introduce an arbitrary decimal."""
    assert HALF_DAY_LEAVE_FRACTION == Decimal("0.5")


# ======================================================================
# The Phase 1 boundary, stated out loud
# ======================================================================

def test_phase_1_does_not_yet_carry_the_half_through_creation(client, login, team):
    """DELIBERATE, AND TEMPORARY. The data model accepts a half; the service does
    not store one yet, and no approval writes a `half_day` attendance row.

    Pinned so the boundary is a decision rather than a silent gap - Phase 2
    wires `create_leave_request` up and this expectation flips to
    `== "first_half"`.
    """
    res = client.post(
        API,
        headers=login("hd-emp@x.com"),
        json={
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "half_day": True,
            "half_day_period": "first_half",
            "reason": "Personal",
        },
    )
    assert res.status_code == 201, res.text
    assert res.json()["half_day_period"] is None


def test_an_incomplete_half_day_request_is_refused_at_the_api(client, login, team):
    """The one half-day rule that IS live end to end in Phase 1: the schema
    refuses it, so the API answers 422 before any row is read."""
    res = client.post(
        API,
        headers=login("hd-emp@x.com"),
        json={
            "start_date": DAY.isoformat(),
            "end_date": DAY.isoformat(),
            "half_day": True,
            "reason": "Personal",
        },
    )
    assert res.status_code == 422, res.text
