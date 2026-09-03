"""Phase 1: leave is Normal (<= 3 working days) or Special (> 3).

Three things are worth proving, and this file is in three parts accordingly:

  1. The RULE itself, as a pure function of a number - including the boundary,
     which is the only place a classification can be got wrong by one.
  2. That the number it is applied to is the AUTHORITATIVE working-day count
     from the company calendar, not the calendar span. This is what makes
     29 Aug - 1 Sep 2026 Special (4 working days) while it looks like 4 calendar
     days that contain only 2 weekdays.
  3. That a company calendar override still moves that count, and therefore can
     still move the classification across the boundary.
  4. That the read-only "Leave type" the request form shows while the employee
     picks dates is that same answer, and not a second opinion.
"""
from datetime import date

import pytest

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.leave.classification import LeaveClassification, classify_leave
from app.modules.leave.effects import leave_working_days


def _classify(db, start: date, end: date) -> LeaveClassification:
    """Exactly what the service does: authoritative count, then the rule."""
    return classify_leave(len(leave_working_days(db, start, end)))


# ---------- 1. the rule ------------------------------------------------------

@pytest.mark.parametrize(
    "working_days,expected",
    [
        (1, LeaveClassification.normal),
        (2, LeaveClassification.normal),
        (3, LeaveClassification.normal),
        (4, LeaveClassification.special),
        (5, LeaveClassification.special),
    ],
)
def test_classify_leave_boundary(working_days, expected):
    assert classify_leave(working_days) is expected


def test_zero_working_days_is_normal():
    """A range that lands entirely on non-working days costs nothing, and
    nothing is not a Special leave."""
    assert classify_leave(0) is LeaveClassification.normal


# ---------- 2. against the real office calendar ------------------------------

# Mon 24 Aug 2026 .. Fri 28 Aug 2026 are ordinary weekdays.
_MON = date(2026, 8, 24)
_TUE = date(2026, 8, 25)
_WED = date(2026, 8, 26)
_THU = date(2026, 8, 27)
_FRI = date(2026, 8, 28)


@pytest.mark.parametrize(
    "end,expected_days,expected",
    [
        (_MON, 1, LeaveClassification.normal),
        (_TUE, 2, LeaveClassification.normal),
        (_WED, 3, LeaveClassification.normal),
        (_THU, 4, LeaveClassification.special),
        (_FRI, 5, LeaveClassification.special),
    ],
)
def test_weekday_ranges(db, end, expected_days, expected):
    assert len(leave_working_days(db, _MON, end)) == expected_days
    assert _classify(db, _MON, end) is expected


def test_weekend_spanning_range_is_classified_on_working_days(db):
    """29 Aug 2026 -> 1 Sep 2026: four calendar days, THREE working ones.

        29 Aug  5th Saturday  working
        30 Aug  Sunday        non-working
        31 Aug  Monday        working
         1 Sep  Tuesday       working

    Only the Sunday drops out, so the range costs 3 days and is NORMAL. The
    span would say 4 and call it Special; the authoritative count is the one
    that decides, which is the whole point of deriving the classification from
    `leave_working_days` rather than from the dates.
    """
    start, end = date(2026, 8, 29), date(2026, 9, 1)
    assert (end - start).days + 1 == 4
    assert leave_working_days(db, start, end) == [
        date(2026, 8, 29),
        date(2026, 8, 31),
        date(2026, 9, 1),
    ]
    assert _classify(db, start, end) is LeaveClassification.normal


def test_one_more_day_makes_that_same_range_special(db):
    """Extend the range above by a single weekday - 29 Aug -> 2 Sep 2026 - and
    the count reaches 4, which is Special. The boundary is crossed by a WORKING
    day being added, never by a weekend day."""
    start, end = date(2026, 8, 29), date(2026, 9, 2)
    assert len(leave_working_days(db, start, end)) == 4
    assert _classify(db, start, end) is LeaveClassification.special


def test_friday_to_monday_is_normal_not_special(db):
    """28 Aug (Fri) -> 31 Aug (Mon) 2026 is 4 calendar days but 3 working ones -
    the 5th Saturday works, the Sunday does not - so it stays Normal. Counting
    the span would wrongly make this Special."""
    assert (date(2026, 8, 31) - date(2026, 8, 28)).days + 1 == 4
    assert len(leave_working_days(db, date(2026, 8, 28), date(2026, 8, 31))) == 3
    assert _classify(db, date(2026, 8, 28), date(2026, 8, 31)) is (
        LeaveClassification.normal
    )


def test_range_over_a_non_working_saturday_is_normal(db):
    """Fri 21 Aug -> Tue 25 Aug 2026 spans the 4th Saturday (off) and a Sunday,
    so it is 3 working days and Normal, despite being 5 calendar days."""
    assert len(leave_working_days(db, date(2026, 8, 21), date(2026, 8, 25))) == 3
    assert _classify(db, date(2026, 8, 21), date(2026, 8, 25)) is (
        LeaveClassification.normal
    )


# ---------- 3. company calendar overrides still decide -----------------------

def _event(db, day: date, event_type: CalendarEventType) -> None:
    db.add(CalendarEvent(event_date=day, title="Test", event_type=event_type))
    db.commit()


def test_holiday_override_pulls_a_range_back_to_normal(db):
    """Mon-Thu is 4 working days and Special. Declare the Wednesday a holiday
    and the same request costs 3 days, so it is Normal - the classification
    follows the calendar, because it is derived rather than stored."""
    assert _classify(db, _MON, _THU) is LeaveClassification.special
    _event(db, _WED, CalendarEventType.holiday)
    assert len(leave_working_days(db, _MON, _THU)) == 3
    assert _classify(db, _MON, _THU) is LeaveClassification.normal


def test_working_day_override_pushes_a_range_to_special(db):
    """Fri 28 Aug -> Mon 31 Aug 2026 is 3 working days (Normal). Declaring the
    Sunday a `working_day` makes it 4, and therefore Special."""
    start, end = date(2026, 8, 28), date(2026, 8, 31)
    assert _classify(db, start, end) is LeaveClassification.normal
    _event(db, date(2026, 8, 30), CalendarEventType.working_day)
    assert len(leave_working_days(db, start, end)) == 4
    assert _classify(db, start, end) is LeaveClassification.special


# ---------- 4. the form's read-only preview ----------------------------------

_PREVIEW = "/api/v1/leave-requests/classification-preview"


@pytest.mark.parametrize(
    "end,expected_days,expected",
    [
        (_WED, 3, "normal"),
        (_THU, 4, "special"),
    ],
)
def test_preview_reports_the_same_answer_the_request_will_get(
    client, make_user, make_employee, login, end, expected_days, expected,
):
    """The dialog shows a frozen Leave type while the dates are being chosen.
    It must be the very number the filed request is read through - anything
    else would promise the employee a classification they do not get."""
    u = make_user("preview@x.com")
    make_employee(employee_code="EP1", user_id=u.id)
    res = client.get(
        _PREVIEW,
        headers=login("preview@x.com"),
        params={"start_date": _MON.isoformat(), "end_date": end.isoformat()},
    )
    assert res.status_code == 200, res.text
    assert res.json()["working_days"] == expected_days
    assert res.json()["classification"] == expected


def test_holiday_override_moves_the_preview_too(
    client, db, make_user, make_employee, login,
):
    """The preview reads the SAME calculation, so a declared holiday changes
    what the employee is shown before they file, not only what they are charged
    afterwards."""
    u = make_user("preview2@x.com")
    make_employee(employee_code="EP2", user_id=u.id)
    h = login("preview2@x.com")
    params = {"start_date": _MON.isoformat(), "end_date": _THU.isoformat()}

    first = client.get(_PREVIEW, headers=h, params=params).json()
    assert (first["working_days"], first["classification"]) == (4, "special")

    _event(db, _WED, CalendarEventType.holiday)
    second = client.get(_PREVIEW, headers=h, params=params).json()
    assert (second["working_days"], second["classification"]) == (3, "normal")


def test_preview_of_an_inverted_range_is_zero_days_not_an_error(
    client, make_user, make_employee, login,
):
    """The form asks as the employee types, so a To date briefly before the
    From date is a half-typed range, not a fault."""
    u = make_user("preview3@x.com")
    make_employee(employee_code="EP3", user_id=u.id)
    res = client.get(
        _PREVIEW,
        headers=login("preview3@x.com"),
        params={"start_date": _THU.isoformat(), "end_date": _MON.isoformat()},
    )
    assert res.status_code == 200, res.text
    assert res.json()["working_days"] == 0
    assert res.json()["classification"] == "normal"


def test_preview_is_not_swallowed_by_the_uuid_route(
    client, make_user, make_employee, login,
):
    """`/classification-preview` is a literal path sitting under the same prefix
    as `GET /{req_id}`. Declared after it, every call would 422 on a bad uuid."""
    u = make_user("preview4@x.com")
    make_employee(employee_code="EP4", user_id=u.id)
    res = client.get(
        _PREVIEW,
        headers=login("preview4@x.com"),
        params={"start_date": _MON.isoformat(), "end_date": _MON.isoformat()},
    )
    assert res.status_code == 200, res.text
