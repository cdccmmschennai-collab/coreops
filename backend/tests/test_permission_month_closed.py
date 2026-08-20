"""A finished month cannot be spent from - but it stays fully readable.

Permission hours are monthly and do not carry forward, so once August is over
there is no August allowance left to draw on. Phase 3 makes that a BACKEND rule:
these tests call the API directly, because hiding a button proves nothing.

Everything else about permission is deliberately untouched, and the second half
of this file pins that: the current month still works exactly as it did, a future
month is still allowed, an old request can still be decided, and the allowance is
still four hours that do not roll over.

Dates are relative to the real Chennai business date, since "which month has
ended" is the thing under test.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.modules.permissions.balance import month_has_closed
from app.modules.permissions.models import PermissionStatus
from app.modules.users.models import UserRole

API = "/api/v1/permission-requests"
IST = ZoneInfo("Asia/Kolkata")


def _today() -> date:
    return datetime.now(IST).date()


def _month_start(value: date) -> date:
    return value.replace(day=1)


def _previous_month(value: date) -> date:
    first = _month_start(value)
    return _month_start(first - timedelta(days=1))


def _next_month(value: date) -> date:
    first = _month_start(value)
    return _month_start(first + timedelta(days=32))


def _a_weekday_in(month: date) -> date:
    """A Mon-Fri date inside `month` - a permission needs a working day.

    The 1st through 7th always contain a weekday, and the company calendar is
    empty in these tests, so `is_working_day` reduces to Mon-Fri.
    """
    for day in range(1, 8):
        candidate = month.replace(day=day)
        if candidate.weekday() < 5:
            return candidate
    raise AssertionError("a week always contains a weekday")


@pytest.fixture()
def team(make_user, make_employee):
    mu = make_user("mgr@pmc.com", role=UserRole.project_manager)
    mgr = make_employee(employee_code="MGR-PMC", user_id=mu.id)
    eu = make_user("emp@pmc.com", role=UserRole.employee)
    emp = make_employee(employee_code="EMP-PMC", user_id=eu.id, manager_id=mgr.id)
    return {"manager": mgr, "employee": emp}


def _submit(client, login, day: date, hours: int = 1):
    return client.post(
        API,
        headers=login("emp@pmc.com"),
        json={
            "permission_date": day.isoformat(),
            "duration_hours": hours,
            "reason": "School run",
        },
    )


def _balance(client, login, month: date) -> dict:
    res = client.get(
        f"{API}/balance/me?month={month.isoformat()}", headers=login("emp@pmc.com")
    )
    assert res.status_code == 200, res.text
    return res.json()


# ======================================================================
# The rule itself
# ======================================================================

def test_month_has_closed_compares_months_not_dates():
    """Pure, so the boundary can be reasoned about without a clock.

    Mid-August, an early-August date is NOT closed - the month it belongs to is
    still running. On 1 September every August date is.
    """
    mid_august = date(2026, 8, 20)
    assert month_has_closed(date(2026, 7, 31), mid_august) is True
    assert month_has_closed(date(2026, 8, 3), mid_august) is False
    assert month_has_closed(date(2026, 8, 31), mid_august) is False
    assert month_has_closed(date(2026, 9, 1), mid_august) is False  # future

    first_september = date(2026, 9, 1)
    assert month_has_closed(date(2026, 8, 31), first_september) is True


def test_month_has_closed_crosses_the_year():
    assert month_has_closed(date(2026, 12, 31), date(2027, 1, 1)) is True
    assert month_has_closed(date(2027, 1, 1), date(2026, 12, 31)) is False


# ======================================================================
# Creation against a closed month
# ======================================================================

def test_a_request_for_last_month_is_refused_by_the_backend(client, login, team):
    """The headline rule. Not a hidden button - a refused API call."""
    last_month = _previous_month(_today())
    res = _submit(client, login, _a_weekday_in(last_month))
    assert res.status_code == 422, res.text
    assert "has ended" in res.json()["error"]["message"]


def test_the_refusal_names_the_month_and_what_to_do_instead(client, login, team):
    last_month = _previous_month(_today())
    message = _submit(client, login, _a_weekday_in(last_month)).json()["error"]["message"]
    assert last_month.strftime("%B %Y") in message
    assert _today().strftime("%B %Y") in message
    assert "don't carry forward" in message


def test_a_request_for_a_month_long_past_is_refused(client, login, team):
    old = _month_start(_today()) - timedelta(days=200)
    res = _submit(client, login, _a_weekday_in(_month_start(old)))
    assert res.status_code == 422, res.text


def test_nothing_is_written_when_a_closed_month_is_refused(client, login, team, db):
    from app.modules.permissions.models import PermissionRequest

    _submit(client, login, _a_weekday_in(_previous_month(_today())))
    assert db.query(PermissionRequest).count() == 0


# ======================================================================
# A closed month stays readable
# ======================================================================

def test_a_closed_months_balance_is_still_reported(client, login, team):
    """History is not hidden - it just cannot be added to."""
    last_month = _previous_month(_today())
    body = _balance(client, login, last_month)
    assert body["month"] == _month_start(last_month).isoformat()
    assert body["allowance_hours"] == 4
    assert body["remaining_hours"] == 4
    assert body["is_current_month"] is False
    assert body["requests_allowed"] is False


def test_a_closed_months_history_is_still_readable(
    client, login, team, make_permission_request
):
    last_month = _previous_month(_today())
    day = _a_weekday_in(last_month)
    make_permission_request(
        employee_id=team["employee"].id,
        permission_date=day,
        duration_hours=1,
        status=PermissionStatus.approved,
    )

    res = client.get(
        f"{API}/history?month={last_month.isoformat()}", headers=login("emp@pmc.com")
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert [i["permission_date"] for i in body["items"]] == [day.isoformat()]
    assert body["balance"]["approved_hours"] == 1
    assert body["balance"]["remaining_hours"] == 3
    assert body["balance"]["requests_allowed"] is False


def test_a_manager_can_still_decide_a_request_filed_before_the_month_ended(
    client, login, team, make_permission_request
):
    """Correcting a past decision is not the same as making a new one, so review
    is deliberately untouched by the closure rule."""
    last_month = _previous_month(_today())
    req = make_permission_request(
        employee_id=team["employee"].id,
        permission_date=_a_weekday_in(last_month),
        duration_hours=2,
        status=PermissionStatus.pending,
    )
    res = client.post(f"{API}/{req.id}/approve", headers=login("mgr@pmc.com"), json={})
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "approved"
    assert _balance(client, login, last_month)["remaining_hours"] == 2


def test_a_manager_can_still_cancel_a_request_in_a_closed_month(
    client, login, team, make_permission_request
):
    last_month = _previous_month(_today())
    req = make_permission_request(
        employee_id=team["employee"].id,
        permission_date=_a_weekday_in(last_month),
        duration_hours=1,
        status=PermissionStatus.approved,
    )
    res = client.post(f"{API}/{req.id}/cancel", headers=login("mgr@pmc.com"))
    assert res.status_code == 200, res.text
    assert _balance(client, login, last_month)["remaining_hours"] == 4


# ======================================================================
# The current month is unchanged
# ======================================================================

def test_the_current_month_still_accepts_a_request(client, login, team):
    """A fresh month, four hours, and the existing rules - nothing new applies."""
    today = _today()
    body = _balance(client, login, today)
    assert body["allowance_hours"] == 4
    assert body["remaining_hours"] == 4
    assert body["is_current_month"] is True
    assert body["requests_allowed"] is True

    res = _submit(client, login, _a_weekday_in(_month_start(today)))
    assert res.status_code == 201, res.text


def test_a_date_earlier_in_the_current_month_is_still_allowed(client, login, team):
    """The rule is about the MONTH, not the date: a day already past inside the
    running month is still that month's allowance, and filing for it is how a
    late request gets recorded."""
    today = _today()
    day = _a_weekday_in(_month_start(today))
    if day >= today:
        pytest.skip("run before the first weekday of the month has passed")
    assert _submit(client, login, day).status_code == 201


def test_the_last_day_of_the_current_month_is_allowed(client, login, team):
    """The boundary, from the inside."""
    today = _today()
    cursor = _next_month(today) - timedelta(days=1)
    while cursor.weekday() >= 5:
        cursor -= timedelta(days=1)
    assert month_has_closed(cursor, today) is False
    assert _submit(client, login, cursor).status_code == 201


def test_a_future_month_is_still_allowed(client, login, team):
    """No future-month policy is invented: filing ahead worked before and works
    now. Only the PAST is closed."""
    ahead = _next_month(_today())
    body = _balance(client, login, ahead)
    assert body["is_current_month"] is False
    assert body["requests_allowed"] is True
    assert _submit(client, login, _a_weekday_in(ahead)).status_code == 201


# ======================================================================
# Still no carry-forward
# ======================================================================

def test_last_months_unused_hours_do_not_reach_this_month(
    client, login, team, make_permission_request
):
    """3h unused in a closed month must not make this month worth 7h."""
    last_month = _previous_month(_today())
    make_permission_request(
        employee_id=team["employee"].id,
        permission_date=_a_weekday_in(last_month),
        duration_hours=1,
        status=PermissionStatus.approved,
    )
    assert _balance(client, login, last_month)["remaining_hours"] == 3
    assert _balance(client, login, _today())["remaining_hours"] == 4


def test_a_fully_spent_closed_month_does_not_reduce_this_month(
    client, login, team, make_permission_request
):
    last_month = _previous_month(_today())
    make_permission_request(
        employee_id=team["employee"].id,
        permission_date=_a_weekday_in(last_month),
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    make_permission_request(
        employee_id=team["employee"].id,
        permission_date=_a_weekday_in(last_month) + timedelta(days=7),
        duration_hours=2,
        status=PermissionStatus.approved,
    )
    assert _balance(client, login, last_month)["remaining_hours"] == 0
    assert _balance(client, login, _today())["remaining_hours"] == 4
