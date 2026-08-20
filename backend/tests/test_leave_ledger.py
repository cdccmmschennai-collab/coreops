"""The leave ledger: monthly accrual, carry-forward, corrections, history.

Everything here goes through `ledger.month_balance`, the single authority the
attendance KPI, the Leave Balance table, the approval guard and the monthly
notification all read. If a rule is not true here it is not true anywhere.

Dates are pinned to 2027 so nothing collides with the real "today", and the
weekday of a date never matters: the ledger counts `attendance_records` rows
that already exist, it does not decide which days are working days.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.attendance.models import AttendanceStatus
from app.modules.leave.models import LeaveStatus, LeaveType
from app.modules.leave_balances import ledger

JAN = date(2027, 1, 1)
FEB = date(2027, 2, 1)
MAR = date(2027, 3, 1)
APR = date(2027, 4, 1)

AUG = date(2027, 8, 1)
SEP = date(2027, 9, 1)
OCT = date(2027, 10, 1)
NOV = date(2027, 11, 1)

DEC = date(2027, 12, 1)
NEXT_JAN = date(2028, 1, 1)


@pytest.fixture()
def employee(make_employee):
    return make_employee(employee_code="LEDGER-1", first_name="Ada", last_name="L")


def _closing(db, employee_id, month) -> Decimal:
    return ledger.closing_balance(db, employee_id, month)


def _take_leave(make_attendance, employee_id, *days: date) -> None:
    """Mark days as `leave` - exactly what an approved leave request writes."""
    for day in days:
        make_attendance(
            employee_id=employee_id,
            attendance_date=day,
            status=AttendanceStatus.leave,
        )


# ======================================================================
# Carry-forward - the worked example from the brief
# ======================================================================

def test_unused_leave_carries_forward_month_after_month(
    db, employee, make_leave_allocation, make_leave_adjustment, make_attendance
):
    """August 1.5 -> September 2.5 -> October 4.5, on 2 days/month.

        August     alloc 2, carry 0,   consumed 0.5*  closing 1.5
        September  alloc 2, carry 1.5, consumed 1     closing 2.5
        October    alloc 2, carry 2.5, consumed 0     closing 4.5

    (*) CoreOps has no half-day leave, so August's 0.5 is expressed as a -0.5
    adjustment - which is also the shape a PM correction takes.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    # August: half a day gone.
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days="-0.5", reason="Half day"
    )
    # September: one full day of leave.
    _take_leave(make_attendance, employee.id, date(2027, 9, 14))

    assert _closing(db, employee.id, AUG) == Decimal("1.50")
    assert _closing(db, employee.id, SEP) == Decimal("2.50")
    assert _closing(db, employee.id, OCT) == Decimal("4.50")


def test_september_opens_with_augusts_closing_balance(
    db, employee, make_leave_allocation, make_attendance
):
    """Carry-forward is not a separate figure - it IS the previous closing."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    _take_leave(make_attendance, employee.id, date(2027, 8, 10))

    august = ledger.month_balance(db, employee.id, AUG)
    september = ledger.month_balance(db, employee.id, SEP)

    assert august.closing == Decimal("1.00")
    assert september.carry_forward == august.closing
    assert september.allocation == Decimal("2.00")
    assert september.closing == Decimal("3.00")


def test_reading_a_month_twice_returns_the_same_figure(
    db, employee, make_leave_allocation
):
    """The accrual is a fold, not an increment: asking again cannot add again.

    This is the refresh-the-page case. Ten reads of August must be ten identical
    answers, or the monthly allocation is being applied on read.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    answers = {_closing(db, employee.id, AUG) for _ in range(10)}
    assert answers == {Decimal("2.00")}


def test_walking_forward_then_back_does_not_change_history(
    db, employee, make_leave_allocation, make_attendance
):
    """August -> September -> October -> August is the same August."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    _take_leave(make_attendance, employee.id, date(2027, 9, 14))

    first = _closing(db, employee.id, AUG)
    _closing(db, employee.id, SEP)
    _closing(db, employee.id, OCT)
    assert _closing(db, employee.id, AUG) == first == Decimal("2.00")


def test_a_month_with_no_activity_still_accrues(
    db, employee, make_leave_allocation
):
    """Nobody has to open the page for a month to accrue. November is answered
    correctly even though nothing at all happened in September or October."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    assert _closing(db, employee.id, NOV) == Decimal("8.00")  # Aug..Nov = 4 x 2


def test_the_ledger_crosses_the_year_boundary(
    db, employee, make_leave_allocation
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=DEC, monthly_days=2
    )
    assert _closing(db, employee.id, DEC) == Decimal("2.00")
    assert _closing(db, employee.id, NEXT_JAN) == Decimal("4.00")


# ======================================================================
# Employee-specific allocation
# ======================================================================

@pytest.mark.parametrize("rate,expected", [(1, "3.00"), (2, "6.00"), (3, "9.00")])
def test_each_employee_accrues_their_own_rate(
    db, make_employee, make_leave_allocation, rate, expected
):
    """1, 2 and 3 days/month over three months. No universal company value."""
    emp = make_employee(employee_code=f"RATE-{rate}", first_name="R", last_name=str(rate))
    make_leave_allocation(
        employee_id=emp.id, effective_from=AUG, monthly_days=rate
    )
    assert _closing(db, emp.id, OCT) == Decimal(expected)


def test_three_employees_on_different_rates_do_not_interfere(
    db, make_employee, make_leave_allocation
):
    rates = {"EMP-A": 1, "EMP-B": 2, "EMP-C": 3}
    emps = {}
    for code, rate in rates.items():
        emp = make_employee(employee_code=code, first_name=code, last_name="X")
        make_leave_allocation(
            employee_id=emp.id, effective_from=AUG, monthly_days=rate
        )
        emps[code] = emp

    for code, rate in rates.items():
        assert _closing(db, emps[code].id, SEP) == Decimal(rate * 2)


def test_a_fractional_allocation_is_supported(
    db, employee, make_leave_allocation
):
    """0.5 d/month - the leave system already deals in halves."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days="0.5"
    )
    assert _closing(db, employee.id, OCT) == Decimal("1.50")


def test_an_employee_with_no_allocation_has_no_ledger(db, employee):
    """No allocation and no adjustment is not a zero balance - it is no ledger.

    The UI shows "-" for this, never "0d", because inventing a zero would claim
    the employee has been assessed when they have not.
    """
    balance = ledger.month_balance(db, employee.id, AUG)
    assert balance.in_ledger is False
    assert balance.ledger_start is None
    assert balance.closing == Decimal("0.00")


def test_a_zero_allocation_is_a_real_ledger_that_only_carries(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """0 d/month is a decision, not an absence of one: the employee is in the
    ledger and keeps whatever they were given, month after month."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=0
    )
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days=3, reason="Opening"
    )
    august = ledger.month_balance(db, employee.id, AUG)
    assert august.in_ledger is True
    assert _closing(db, employee.id, OCT) == Decimal("3.00")


# ======================================================================
# Allocation changes must not rewrite history
# ======================================================================

def test_raising_the_rate_in_march_leaves_january_and_february_alone(
    db, employee, make_leave_allocation
):
    """January = 1d, February = 1d, March onward = 2d.

    The brief's central historical-correctness case. The March row is a SECOND
    row, so the January row stays in force for January however the current
    figure is edited later.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=JAN, monthly_days=1
    )
    make_leave_allocation(
        employee_id=employee.id, effective_from=MAR, monthly_days=2
    )

    assert ledger.month_balance(db, employee.id, JAN).allocation == Decimal("1.00")
    assert ledger.month_balance(db, employee.id, FEB).allocation == Decimal("1.00")
    assert ledger.month_balance(db, employee.id, MAR).allocation == Decimal("2.00")
    assert ledger.month_balance(db, employee.id, APR).allocation == Decimal("2.00")

    # 1 + 1 + 2 + 2
    assert _closing(db, employee.id, APR) == Decimal("6.00")


def test_a_future_dated_rate_change_does_not_apply_yet(
    db, employee, make_leave_allocation
):
    """A rate effective September accrues nothing in August."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    make_leave_allocation(
        employee_id=employee.id, effective_from=SEP, monthly_days=3
    )
    assert ledger.month_balance(db, employee.id, AUG).allocation == Decimal("2.00")
    assert ledger.month_balance(db, employee.id, SEP).allocation == Decimal("3.00")


def test_allocation_in_force_is_pure_and_needs_no_database():
    """The effective-dating rule on its own, so it can be reasoned about."""
    rows = [(JAN, Decimal("1")), (MAR, Decimal("2"))]
    assert ledger.allocation_in_force(rows, JAN) == Decimal("1")
    assert ledger.allocation_in_force(rows, FEB) == Decimal("1")
    assert ledger.allocation_in_force(rows, MAR) == Decimal("2")
    assert ledger.allocation_in_force(rows, date(2027, 3, 31)) == Decimal("2")
    # Before the first row there is no rate at all.
    assert ledger.allocation_in_force(rows, date(2026, 12, 1)) == Decimal("0")


# ======================================================================
# PM correction
# ======================================================================

def test_a_correction_adds_to_the_automatic_balance(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """automatic + adjustment = effective. 2.5 - 0.5 = 2.0."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days="0.5", reason="Goodwill"
    )
    august = ledger.month_balance(db, employee.id, AUG)
    assert august.allocation == Decimal("2.00")
    assert august.adjustment == Decimal("0.50")
    assert august.closing == Decimal("2.50")


def test_a_correction_does_not_stop_the_next_month_accruing(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """The brief's §9: a September correction must not disable October's 2 days.

    A correction is a ledger TERM, not a replacement of the configuration.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=SEP, monthly_days=2
    )
    make_leave_adjustment(
        employee_id=employee.id, effective_month=SEP, days=1, reason="Opening"
    )
    assert _closing(db, employee.id, SEP) == Decimal("3.00")

    make_leave_adjustment(
        employee_id=employee.id, effective_month=SEP, days=-1, reason="Correction"
    )
    assert _closing(db, employee.id, SEP) == Decimal("2.00")
    # October still gets its own 2 days on top of the corrected September.
    assert _closing(db, employee.id, OCT) == Decimal("4.00")


def test_several_corrections_in_one_month_all_count(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """Each correction is an event. The last one does not win - they sum."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    for days in (1, -0.5, 2):
        make_leave_adjustment(
            employee_id=employee.id, effective_month=AUG, days=days
        )
    assert ledger.month_balance(db, employee.id, AUG).adjustment == Decimal("2.50")
    assert _closing(db, employee.id, AUG) == Decimal("4.50")


def test_a_correction_stays_in_the_month_it_was_made_for(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """A September correction is invisible in August, forever."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    make_leave_adjustment(
        employee_id=employee.id, effective_month=SEP, days=5, reason="Late correction"
    )
    assert _closing(db, employee.id, AUG) == Decimal("2.00")
    assert _closing(db, employee.id, SEP) == Decimal("9.00")


# ======================================================================
# Negative balances
# ======================================================================

def test_a_negative_balance_is_representable(
    db, employee, make_leave_adjustment
):
    """Loss-of-pay. Nothing is clamped at zero, here or in the schema."""
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days=-1, reason="LOP"
    )
    assert _closing(db, employee.id, AUG) == Decimal("-1.00")


def test_a_negative_month_carries_its_deficit_forward(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """A deficit is carried like any other balance - it is not reset to zero."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=1
    )
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days=-3, reason="LOP"
    )
    assert _closing(db, employee.id, AUG) == Decimal("-2.00")
    assert _closing(db, employee.id, SEP) == Decimal("-1.00")
    assert _closing(db, employee.id, OCT) == Decimal("0.00")


def test_consuming_more_than_the_balance_goes_negative_not_zero(
    db, employee, make_leave_allocation, make_attendance
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=1
    )
    _take_leave(
        make_attendance,
        employee.id,
        date(2027, 8, 3),
        date(2027, 8, 4),
        date(2027, 8, 5),
    )
    assert _closing(db, employee.id, AUG) == Decimal("-2.00")


# ======================================================================
# Consumption
# ======================================================================

def test_consumption_is_counted_in_the_month_the_day_falls_in(
    db, employee, make_leave_allocation, make_attendance
):
    """A leave straddling a month boundary is charged to both months, per day."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=3
    )
    _take_leave(
        make_attendance,
        employee.id,
        date(2027, 8, 30),
        date(2027, 8, 31),
        date(2027, 9, 1),
    )
    assert ledger.month_balance(db, employee.id, AUG).consumed == Decimal("2.00")
    assert ledger.month_balance(db, employee.id, SEP).consumed == Decimal("1.00")


def test_a_half_day_attendance_record_is_not_leave(
    db, employee, make_leave_allocation, make_attendance
):
    """`half_day` is half a WORKING day, not half a day of leave.

    Every `half_day` row in the production database falls on one company-wide
    half day; charging those employees half a day of leave each would be wrong.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    make_attendance(
        employee_id=employee.id,
        attendance_date=date(2027, 8, 14),
        status=AttendanceStatus.half_day,
    )
    assert ledger.month_balance(db, employee.id, AUG).consumed == Decimal("0.00")
    assert _closing(db, employee.id, AUG) == Decimal("2.00")


def test_present_absent_holiday_and_comp_off_are_not_leave(
    db, employee, make_leave_allocation, make_attendance
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    for offset, status in enumerate(
        (
            AttendanceStatus.present,
            AttendanceStatus.absent,
            AttendanceStatus.holiday,
            AttendanceStatus.comp_off,
        ),
        start=3,
    ):
        make_attendance(
            employee_id=employee.id,
            attendance_date=date(2027, 8, offset),
            status=status,
        )
    assert ledger.month_balance(db, employee.id, AUG).consumed == Decimal("0.00")


def test_unpaid_leave_days_are_marked_but_not_deducted(
    db, employee, make_leave_allocation, make_attendance, make_leave_request
):
    """Unpaid absence is by definition not funded from the leave pool - the same
    rule `effects.BALANCE_DEDUCTING_TYPES` already applies at approval."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    make_leave_request(
        employee_id=employee.id,
        leave_type=LeaveType.unpaid,
        start_date=date(2027, 8, 10),
        end_date=date(2027, 8, 11),
        status=LeaveStatus.approved,
    )
    _take_leave(make_attendance, employee.id, date(2027, 8, 10), date(2027, 8, 11))

    assert ledger.month_balance(db, employee.id, AUG).consumed == Decimal("0.00")
    assert _closing(db, employee.id, AUG) == Decimal("2.00")


def test_a_paid_day_beside_an_unpaid_range_still_counts(
    db, employee, make_leave_allocation, make_attendance, make_leave_request
):
    """Only the days the unpaid request actually covers are exempt."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=5
    )
    make_leave_request(
        employee_id=employee.id,
        leave_type=LeaveType.unpaid,
        start_date=date(2027, 8, 10),
        end_date=date(2027, 8, 10),
        status=LeaveStatus.approved,
    )
    _take_leave(make_attendance, employee.id, date(2027, 8, 10), date(2027, 8, 12))
    assert ledger.month_balance(db, employee.id, AUG).consumed == Decimal("1.00")


def test_removing_the_attendance_rows_restores_the_balance_exactly(
    db, employee, make_leave_allocation, make_attendance
):
    """Cancellation, in ledger terms.

    `reverse_leave_approved` deletes the rows an approval wrote; consumption then
    drops by exactly the number removed. There is no counter to over-credit, so
    "cancel twice" cannot restore twice - the second attempt removes nothing.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    rows = [
        make_attendance(
            employee_id=employee.id,
            attendance_date=day,
            status=AttendanceStatus.leave,
        )
        for day in (date(2027, 8, 10), date(2027, 8, 11))
    ]
    assert _closing(db, employee.id, AUG) == Decimal("0.00")

    db.delete(rows[0])
    db.commit()
    assert _closing(db, employee.id, AUG) == Decimal("1.00")

    db.delete(rows[1])
    db.commit()
    assert _closing(db, employee.id, AUG) == Decimal("2.00")
    # Nothing left to remove - a repeat reversal cannot push it to 3.
    assert _closing(db, employee.id, AUG) == Decimal("2.00")


def test_a_pending_or_rejected_leave_consumes_nothing(
    db, employee, make_leave_allocation, make_leave_request
):
    """Neither writes attendance rows, so neither can reach the ledger."""
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    for status in (LeaveStatus.pending, LeaveStatus.rejected, LeaveStatus.cancelled):
        make_leave_request(
            employee_id=employee.id,
            start_date=date(2027, 8, 10),
            end_date=date(2027, 8, 10),
            status=status,
        )
    assert _closing(db, employee.id, AUG) == Decimal("2.00")


# ======================================================================
# Before the ledger begins
# ======================================================================

def test_a_month_before_the_ledger_starts_is_not_in_the_ledger(
    db, employee, make_leave_allocation
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=SEP, monthly_days=2
    )
    august = ledger.month_balance(db, employee.id, AUG)
    assert august.in_ledger is False
    assert august.ledger_start == SEP
    assert august.closing == Decimal("0.00")

    september = ledger.month_balance(db, employee.id, SEP)
    assert september.in_ledger is True
    assert september.carry_forward == Decimal("0.00")


def test_leave_taken_before_the_ledger_starts_is_not_charged_to_it(
    db, employee, make_leave_allocation, make_attendance
):
    """The ledger begins where it begins. Absences from before it are history the
    opening balance already accounts for, and must not be deducted twice."""
    _take_leave(make_attendance, employee.id, date(2027, 7, 5), date(2027, 7, 6))
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    assert _closing(db, employee.id, AUG) == Decimal("2.00")


def test_the_ledger_starts_at_the_earliest_row_of_either_kind(
    db, employee, make_leave_allocation, make_leave_adjustment
):
    """An opening adjustment with no allocation still starts a ledger - which is
    the state migration 0069 leaves every existing employee in."""
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days=3, reason="Opening"
    )
    make_leave_allocation(
        employee_id=employee.id, effective_from=OCT, monthly_days=2
    )
    assert ledger.ledger_start(db, employee.id) == AUG
    assert _closing(db, employee.id, AUG) == Decimal("3.00")
    assert _closing(db, employee.id, SEP) == Decimal("3.00")  # no rate yet
    assert _closing(db, employee.id, OCT) == Decimal("5.00")


# ======================================================================
# What the approval guard weighs a request against
# ======================================================================

def test_spendable_is_the_balance_of_the_leaves_own_month(
    db, employee, make_leave_allocation
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    assert ledger.spendable_on(db, employee.id, date(2027, 8, 12)) == Decimal("2.00")
    assert ledger.spendable_on(db, employee.id, date(2027, 10, 12)) == Decimal("6.00")


def test_spendable_counts_leave_already_booked_in_earlier_months(
    db, employee, make_leave_allocation, make_attendance
):
    """Why the guard cannot read "the balance today".

    Two future leaves in different months must not both be weighed against the
    same untouched figure - October's booking has to reduce what November sees,
    or the same days get granted twice.
    """
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    # 3 days taken in October: Aug+Sep+Oct = 6, minus 3.
    _take_leave(
        make_attendance,
        employee.id,
        date(2027, 10, 5),
        date(2027, 10, 6),
        date(2027, 10, 7),
    )
    assert ledger.spendable_on(db, employee.id, date(2027, 11, 3)) == Decimal("5.00")


def test_spendable_before_the_ledger_falls_back_to_its_first_month(
    db, employee, make_leave_adjustment
):
    """The ledger has nothing truthful to say about a month it did not cover, so
    a pre-ledger leave is weighed against the balance carried into it - not
    refused outright, which is what answering zero would do."""
    make_leave_adjustment(
        employee_id=employee.id, effective_month=AUG, days=3, reason="Opening"
    )
    assert ledger.spendable_on(db, employee.id, date(2027, 5, 4)) == Decimal("3.00")


def test_an_employee_with_no_ledger_has_nothing_spendable(db, employee):
    """The same answer the stored balance gave for an employee with no row."""
    assert ledger.spendable_on(db, employee.id, date(2027, 8, 12)) == Decimal("0")


# ======================================================================
# Series and bulk reads
# ======================================================================

def test_the_series_reports_every_month_from_the_start(
    db, employee, make_leave_allocation
):
    make_leave_allocation(
        employee_id=employee.id, effective_from=AUG, monthly_days=2
    )
    series = ledger.month_series(db, employee.id, OCT)
    assert [m.month for m in series] == [AUG, SEP, OCT]
    assert [m.closing for m in series] == [
        Decimal("2.00"),
        Decimal("4.00"),
        Decimal("6.00"),
    ]


def test_bulk_read_answers_each_employee_from_their_own_ledger(
    db, make_employee, make_leave_allocation
):
    a = make_employee(employee_code="BULK-A", first_name="A", last_name="A")
    b = make_employee(employee_code="BULK-B", first_name="B", last_name="B")
    make_leave_allocation(employee_id=a.id, effective_from=AUG, monthly_days=1)
    make_leave_allocation(employee_id=b.id, effective_from=SEP, monthly_days=3)

    balances = ledger.closing_balances(db, [a.id, b.id], SEP)
    assert balances[a.id].closing == Decimal("2.00")
    assert balances[b.id].closing == Decimal("3.00")
    assert balances[b.id].carry_forward == Decimal("0.00")


def test_employees_with_ledger_lists_only_those_already_started(
    db, make_employee, make_leave_allocation, make_leave_adjustment
):
    started = make_employee(employee_code="ON", first_name="On", last_name="X")
    later = make_employee(employee_code="LATER", first_name="Later", last_name="X")
    never = make_employee(employee_code="NEVER", first_name="Never", last_name="X")
    make_leave_adjustment(
        employee_id=started.id, effective_month=AUG, days=1, reason="Opening"
    )
    make_leave_allocation(
        employee_id=later.id, effective_from=OCT, monthly_days=2
    )

    audience = set(ledger.employees_with_ledger(db, AUG))
    assert started.id in audience
    assert later.id not in audience
    assert never.id not in audience


# ======================================================================
# Month arithmetic
# ======================================================================

def test_month_helpers_cross_the_year_correctly():
    assert ledger.next_month(date(2027, 12, 9)) == date(2028, 1, 1)
    assert ledger.previous_month(date(2027, 1, 9)) == date(2026, 12, 1)
    assert ledger.month_start(date(2027, 2, 28)) == date(2027, 2, 1)
    assert ledger.month_end(date(2027, 2, 5)) == date(2027, 2, 28)
    # 2028 is a leap year - the end of February must not be hard-coded.
    assert ledger.month_end(date(2028, 2, 5)) == date(2028, 2, 29)


def test_months_between_is_inclusive_and_never_wraps():
    assert ledger.months_between(date(2027, 12, 3), date(2028, 2, 20)) == [
        date(2027, 12, 1),
        date(2028, 1, 1),
        date(2028, 2, 1),
    ]
    assert ledger.months_between(AUG, AUG) == [AUG]
    assert ledger.months_between(SEP, AUG) == []
