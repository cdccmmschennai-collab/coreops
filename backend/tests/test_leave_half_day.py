"""Half-day leave accounting, end to end.

THE BUG THIS PINS DOWN
======================
`attendance_records` had no way to say how much of a day was leave. `status`
alone cannot: `half_day` means "worked half the day" and says nothing about the
other half, so a half-day LEAVE and a company-wide half day were the same row.
The ledger priced every marked day at a flat 1 and ignored `half_day` entirely,
so a half-day leave cost the employee nothing and the balance read 0.5 too high.

Migration 0083 adds the missing quantity and `ledger.leave_days_for` is the one
place a row is priced. The cases below are the brief's nine, in order.

Dates are pinned to 2027 so nothing collides with the real "today". The weekday
of a date never matters here: the ledger counts rows that already exist, it does
not decide which days are working days.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceStatus
from app.modules.leave_balances import ledger
from app.modules.users.models import UserRole
from app.shared.leave_units import is_half_step

API = "/api/v1/leave-balances"

MAR = date(2027, 3, 1)

D1 = date(2027, 3, 2)
D2 = date(2027, 3, 3)
D3 = date(2027, 3, 4)


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="HALF-1", first_name="Mira", last_name="H")


@pytest.fixture()
def pm_headers(client, make_user, make_employee, login):
    """A signed-in project manager - the only role that may correct a balance."""
    user = make_user("pm@halfday.com", role=UserRole.project_manager)
    make_employee(
        employee_code="HALF-PM", first_name="Priya", last_name="M", user_id=user.id
    )
    return login("pm@halfday.com")


@pytest.fixture()
def funded(make_leave_allocation, employee):
    """A pool big enough that nothing under test is clipped by an empty balance."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=MAR, monthly_days=3.5
    )
    return employee


def _consumed(db, employee_id) -> Decimal:
    return ledger.month_balance(db, employee_id, MAR).consumed


def _closing(db, employee_id) -> Decimal:
    return ledger.closing_balance(db, employee_id, MAR)


def _full_day(make_attendance, employee_id, day):
    return make_attendance(
        employee_id=employee_id, attendance_date=day, status=AttendanceStatus.leave
    )


def _half_day_leave(make_attendance, employee_id, day):
    """What the PM records for a half-day leave: worked half, leave half."""
    return make_attendance(
        employee_id=employee_id,
        attendance_date=day,
        status=AttendanceStatus.half_day,
        leave_day_fraction="0.5",
    )


# ======================================================================
# Case 1 - a full day still costs exactly one day
# ======================================================================

def test_case_1_full_day_leave_costs_one_day(db, funded, make_attendance):
    """The behaviour that already worked, pinned so the fix cannot move it."""
    _full_day(make_attendance, funded.id, D1)

    assert _consumed(db, funded.id) == Decimal("1.00")
    assert _closing(db, funded.id) == Decimal("2.50")  # 3.5 - 1


# ======================================================================
# Case 2 - a half day costs half a day (the bug)
# ======================================================================

def test_case_2_half_day_leave_costs_half_a_day(db, funded, make_attendance):
    """Was 0 before migration 0083: the row was invisible to the ledger."""
    _half_day_leave(make_attendance, funded.id, D1)

    assert _consumed(db, funded.id) == Decimal("0.50")
    assert _closing(db, funded.id) == Decimal("3.00")  # 3.5 - 0.5


# ======================================================================
# Case 3 - a full day and a half day
# ======================================================================

def test_case_3_full_plus_half_is_one_and_a_half(db, funded, make_attendance):
    """The exact production symptom: leave taken 1.5, not 1."""
    _full_day(make_attendance, funded.id, D1)
    _half_day_leave(make_attendance, funded.id, D2)

    assert _consumed(db, funded.id) == Decimal("1.50")
    assert _closing(db, funded.id) == Decimal("2.00")  # 3.5 - 1.5


# ======================================================================
# Case 4 - two half days make a whole one
# ======================================================================

def test_case_4_two_half_days_make_one_day(db, funded, make_attendance):
    """Halves add up rather than each rounding to a day or to nothing."""
    _half_day_leave(make_attendance, funded.id, D1)
    _half_day_leave(make_attendance, funded.id, D2)

    assert _consumed(db, funded.id) == Decimal("1.00")
    assert _closing(db, funded.id) == Decimal("2.50")


def test_three_half_days_do_not_drift(db, funded, make_attendance):
    """0.5 three times is 1.5 exactly - Decimal all the way, no float drift."""
    for day in (D1, D2, D3):
        _half_day_leave(make_attendance, funded.id, day)

    assert _consumed(db, funded.id) == Decimal("1.50")


# ======================================================================
# Case 5 - the balance arithmetic
# ======================================================================

def test_case_5_balance_of_three_point_five_less_one_point_five_is_two(
    db, funded, make_attendance
):
    """3.5 available, 1.5 taken, 2 left - the brief's worked example."""
    _full_day(make_attendance, funded.id, D1)
    _half_day_leave(make_attendance, funded.id, D2)

    balance = ledger.month_balance(db, funded.id, MAR)
    assert balance.available == Decimal("3.50")
    assert balance.consumed == Decimal("1.50")
    assert balance.closing == Decimal("2.00")


def test_half_day_carries_forward_as_a_half(
    db, funded, make_attendance, make_leave_allocation
):
    """A half day spent in March is still half a day missing in April.

    Carry-forward is the previous closing, so a fractional consumption has to
    survive the month boundary intact rather than being rounded into it.
    """
    _half_day_leave(make_attendance, funded.id, D1)
    make_leave_allocation(
        employee_id=funded.id, effective_from=date(2027, 4, 1), monthly_days=1
    )

    april = ledger.month_balance(db, funded.id, date(2027, 4, 1))
    assert april.carry_forward == Decimal("3.00")
    assert april.closing == Decimal("4.00")


# ======================================================================
# Cases 6-9 - the balance a PM may type
# ======================================================================

@pytest.mark.parametrize("bad", [2.1, 2.4, 2.25, 0.1, 1.1, 2.6, -0.25])
def test_cases_6_7_invalid_decimals_are_refused(
    client, pm_headers, employee, bad
):
    """2.1 and 2.4 are not quantities of leave, and are refused at the API.

    Not rounded. Rounding 2.4 up credits half a day nobody granted and rounding
    it down takes half a day away silently; both invent a decision the manager
    did not make.
    """
    res = client.post(
        f"{API}/{employee.id}",
        json={"available_leave": bad, "reason": "typo"},
        headers=pm_headers,
    )
    assert res.status_code == 422, res.text


@pytest.mark.parametrize("good", [2.5, 2.0, 0.5, 3.5, -0.5, -2.0])
def test_case_8_9_half_steps_and_zero_are_accepted(
    client, pm_headers, employee, good
):
    """Whole and half days pass, including zero and a negative (loss-of-pay)."""
    res = client.post(
        f"{API}/{employee.id}",
        json={"available_leave": good, "reason": "correction"},
        headers=pm_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["available_leave"] == good


def test_case_9_zero_is_accepted(client, pm_headers, employee):
    res = client.post(
        f"{API}/{employee.id}",
        json={"available_leave": 0, "reason": "reset"},
        headers=pm_headers,
    )
    assert res.status_code == 200, res.text
    assert res.json()["available_leave"] == 0


@pytest.mark.parametrize("bad", [1.1, 2.4, 0.75])
def test_the_monthly_rate_is_half_steps_too(client, pm_headers, employee, bad):
    """An invalid RATE would mint invalid balances every month afterwards."""
    res = client.put(
        f"{API}/{employee.id}/allocation",
        json={"monthly_days": bad, "effective_from": "2027-03-01"},
        headers=pm_headers,
    )
    assert res.status_code == 422, res.text


# ======================================================================
# The pricing rule itself
# ======================================================================

def test_a_stated_fraction_beats_the_status():
    assert ledger.leave_days_for(AttendanceStatus.half_day, Decimal("0.5")) == Decimal(
        "0.50"
    )
    assert ledger.leave_days_for(AttendanceStatus.leave, Decimal("0.5")) == Decimal(
        "0.50"
    )


def test_an_unstated_fraction_keeps_the_old_rule():
    """The pre-0083 reading, exactly - this is what protects historical rows."""
    assert ledger.leave_days_for(AttendanceStatus.leave, None) == Decimal("1")
    assert ledger.leave_days_for(AttendanceStatus.half_day, None) == Decimal("0")


def test_a_stated_zero_is_not_the_same_as_saying_nothing():
    """A manager stating "this half day cost no leave" has said something."""
    assert ledger.leave_days_for(AttendanceStatus.half_day, Decimal("0")) == Decimal("0")


@pytest.mark.parametrize(
    "status",
    [
        AttendanceStatus.present,
        AttendanceStatus.absent,
        AttendanceStatus.holiday,
        AttendanceStatus.weekend,
        AttendanceStatus.comp_off,
    ],
)
def test_days_that_are_not_absence_never_cost_leave(status):
    assert ledger.leave_days_for(status, Decimal("1")) == Decimal("0")


# ======================================================================
# Production data safety
# ======================================================================

def test_a_company_half_day_is_still_free(db, funded, make_attendance):
    """The 29 rows on 2026-08-14 must not be charged to anybody.

    A `half_day` row with no fraction is exactly what a company-wide half day
    looks like in this database, and it still costs nothing. That is the whole
    reason the fraction is stated on the row rather than inferred from the
    status: inferring 0.5 here would silently bill 29 employees for an office
    closure.
    """
    make_attendance(
        employee_id=funded.id,
        attendance_date=D1,
        status=AttendanceStatus.half_day,
    )

    assert _consumed(db, funded.id) == Decimal("0.00")
    assert _closing(db, funded.id) == Decimal("3.50")


def test_unpaid_leave_is_still_free_at_any_fraction(
    db, funded, make_attendance, make_leave_request
):
    """Unpaid absence costs the pool nothing, half a day of it included."""
    from app.modules.leave.models import LeaveStatus, LeaveType

    make_leave_request(
        employee_id=funded.id,
        leave_type=LeaveType.unpaid,
        start_date=D1,
        end_date=D1,
        status=LeaveStatus.approved,
    )
    _half_day_leave(make_attendance, funded.id, D1)

    assert _consumed(db, funded.id) == Decimal("0.00")


# ======================================================================
# The PM's write path - how a half-day leave is actually recorded
# ======================================================================

ATTENDANCE = "/api/v1/attendance"


def test_a_pm_can_record_a_half_day_leave_and_it_costs_half(
    db, client, pm_headers, funded
):
    """The whole fix, through HTTP: record the day, the balance moves by 0.5."""
    res = client.post(
        ATTENDANCE,
        json={
            "employee_id": str(funded.id),
            "attendance_date": D1.isoformat(),
            "status": "half_day",
            "leave_day_fraction": 0.5,
            "note": "Half-day leave",
        },
        headers=pm_headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["leave_day_fraction"] == 0.5

    assert _consumed(db, funded.id) == Decimal("0.50")
    assert _closing(db, funded.id) == Decimal("3.00")


def test_a_half_day_recorded_without_a_fraction_still_costs_nothing(
    db, client, pm_headers, funded
):
    """The company half day, recorded exactly as it always was."""
    res = client.post(
        ATTENDANCE,
        json={
            "employee_id": str(funded.id),
            "attendance_date": D1.isoformat(),
            "status": "half_day",
        },
        headers=pm_headers,
    )
    assert res.status_code == 201, res.text
    assert res.json()["leave_day_fraction"] is None
    assert _consumed(db, funded.id) == Decimal("0.00")


@pytest.mark.parametrize("bad", [0.4, 0.25, 0.75, 1.5, -0.5])
def test_an_invalid_fraction_is_refused_at_the_api(client, pm_headers, funded, bad):
    """0 to 1, in halves. 1.5 of a day is not a day, and 0.4 is not leave."""
    res = client.post(
        ATTENDANCE,
        json={
            "employee_id": str(funded.id),
            "attendance_date": D1.isoformat(),
            "status": "half_day",
            "leave_day_fraction": bad,
        },
        headers=pm_headers,
    )
    assert res.status_code == 422, res.text


def test_a_worked_day_cannot_be_charged_to_the_leave_pool(
    client, pm_headers, funded
):
    """A fraction on a `present` day is a caller mistake, not a silent no-op."""
    res = client.post(
        ATTENDANCE,
        json={
            "employee_id": str(funded.id),
            "attendance_date": D1.isoformat(),
            "status": "present",
            "leave_day_fraction": 0.5,
        },
        headers=pm_headers,
    )
    assert res.status_code == 422, res.text


def test_moving_a_half_day_leave_to_present_stops_charging_it(
    db, client, pm_headers, funded, make_attendance
):
    """The charge does not outlive the status that justified it.

    A PATCH that only changes the status must not leave 0.5 stranded on a
    `present` row - the day would keep costing leave that nothing on screen
    explains.
    """
    record = _half_day_leave(make_attendance, funded.id, D1)
    assert _consumed(db, funded.id) == Decimal("0.50")

    res = client.patch(
        f"{ATTENDANCE}/{record.id}",
        json={"status": "present"},
        headers=pm_headers,
    )
    assert res.status_code == 200, res.text

    db.expire_all()
    assert _consumed(db, funded.id) == Decimal("0.00")


def test_unticking_the_charge_restores_the_balance(
    db, client, pm_headers, funded, make_attendance
):
    """A day wrongly marked as half-day leave can be un-marked."""
    record = _half_day_leave(make_attendance, funded.id, D1)

    res = client.patch(
        f"{ATTENDANCE}/{record.id}",
        json={"status": "half_day", "leave_day_fraction": 0},
        headers=pm_headers,
    )
    assert res.status_code == 200, res.text

    db.expire_all()
    assert _consumed(db, funded.id) == Decimal("0.00")
    assert _closing(db, funded.id) == Decimal("3.50")


# ======================================================================
# The half-step helper
# ======================================================================

@pytest.mark.parametrize("good", [0, 0.5, 1, 1.5, 2, 2.5, 3, 3.5, -0.5, -2])
def test_half_steps_are_recognised(good):
    assert is_half_step(good)


@pytest.mark.parametrize("bad", [0.1, 0.25, 1.1, 1.25, 2.1, 2.4, 2.6, 0.75])
def test_arbitrary_decimals_are_not_half_steps(bad):
    assert not is_half_step(bad)


def test_the_check_reads_the_decimal_the_caller_wrote():
    """0.7 is not half a day, however the binary expansion of it rounds.

    `Decimal(0.7)` is 0.6999999999999999555910790149937383830547332763671875 and
    `% 0.5` on it is nowhere near zero either way, so the check has to go through
    `str` to test the number the manager actually typed. Pinned because
    `Decimal(value)` is the obvious spelling and it judges a different number.
    """
    assert not is_half_step(0.7)
    assert is_half_step(1.5)
    # A whole-day float that is exactly representable must still pass.
    assert is_half_step(2.0)


