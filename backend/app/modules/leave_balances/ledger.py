"""The one place an employee's leave balance is calculated.

THE FORMULA
===========
For one employee and one calendar month M:

    carry_in(M)   = closing(M - 1), and 0 for the ledger's first month
    allocation(M) = the `monthly_days` of the newest EmployeeLeaveAllocation row
                    whose effective_from <= first day of M, else 0
    adjustment(M) = SUM(days) of the EmployeeLeaveAdjustment rows stamped M
    consumed(M)   = leave days actually marked on the calendar in M
    available(M)  = carry_in(M) + allocation(M) + adjustment(M)
    closing(M)    = available(M) - consumed(M)

`closing(M)` is the "Available Leave" figure for month M - on the attendance
KPI, in the Leave Balance table, in the approval guard and in the monthly
notification. There is no second calculation anywhere.

DERIVED, NEVER STORED
=====================
Nothing here writes. The balance is a fold over immutable rows, recomputed on
every read, which is what makes the required properties true by construction
rather than by maintenance:

  refreshing the page      cannot accrue twice - the month contributes its
                           allocation once because the fold visits it once
  navigating back a month  cannot change history - the inputs for August do not
                           depend on when August is asked about
  cancelling leave         restores exactly what it took - `reverse_leave_approved`
                           deletes the attendance rows, so consumed(M) drops by
                           the number actually removed and there is no counter
                           to over-credit
  rejecting leave          costs nothing - it writes no attendance rows
  changing Leave/month     cannot rewrite the past - allocation(M) reads the row
                           in force at M, not the newest row overall

BEFORE THE LEDGER STARTS
========================
An employee's ledger begins at `ledger_start` - the earliest month carrying
either an allocation or an adjustment (for everyone migrated by 0069, the
opening-balance month). A month before that has no ledger at all, which is NOT
the same as a zero balance, so `MonthBalance.in_ledger` is False and the UI
shows "-" rather than inventing 0d. An employee with no rows at all has no
ledger and every month reads as not-in-ledger.

NEGATIVES ARE REAL
==================
Nothing is clamped. The existing system represents loss-of-pay as a negative
balance, PM corrections may push a month below zero, an approved leave the pool
could not fund pushes it below zero too, and this module reports all of that
faithfully.

A negative balance FORBIDS nothing. Leave approval deliberately does not weigh
the balance at all (`leave/service.py::approve_leave_request`): the approver
decides whether the absence is warranted, and a deficit is then carried and
reconciled here rather than refused there. `carry_in(M) = closing(M-1)` is
unclamped, so a deficit survives into the next month, and `available(M)` adds
that month's allocation to it - which is precisely how a negative balance is
offset by future accrual, with no reconciliation step of its own: -2 followed by
+1/month reads -1, then 0.

WHAT COUNTS AS CONSUMED
=======================
The `attendance_records` rows with status `leave` - the same rows the calendar
paints amber and the same rows an approval writes. Not the leave requests: most
of the requests in this database predate the phase that started marking days, so
counting requests would charge people for absences that were never marked, and
the KPI would disagree with the calendar sitting under it.

HOW MUCH A MARKED DAY COSTS
===========================
`leave_days_for` is the only function that turns an attendance row into a number
of leave days, and it reads the row's `leave_day_fraction` (migration 0083):

    fraction stated   ->  that fraction        1 / 0.5 / 0
    fraction NULL     ->  `leave` -> 1, anything else -> 0

The NULL branch is the rule this module applied before the column existed, kept
exactly, so no row written before 0083 changes what it contributes.

WHY THE FRACTION HAD TO EXIST
=============================
`status` cannot answer "how much leave was this day". `half_day` means the
employee worked half the day and says nothing about the other half:

  a half-day LEAVE       worked 0.5, leave 0.5  - the pool pays for the half off
  a company half day     worked 0.5, leave 0    - the office shut at noon

Both are `status = half_day` with no times, and they are indistinguishable in the
row. This module used to treat every one of them as the second case - which is
why the 29 `half_day` rows on 2026-08-14 (a company-wide half day) were correctly
free, and why a genuine half-day leave was ALSO free and silently under-charged
the employee by 0.5. Neither reading is right for both, so the fraction is now
stated on the row instead of inferred from a status that does not carry it.

One deliberate exclusion remains:

  `unpaid` leave      is absence that is BY DEFINITION not funded from the leave
                      pool (`effects.BALANCE_DEDUCTING_TYPES` already excludes
                      it), so its days are marked on the calendar but subtracted
                      from nothing.
"""
from __future__ import annotations

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.leave.models import LeaveRequest, LeaveStatus, LeaveType
from app.modules.leave_balances.models import (
    EmployeeLeaveAdjustment,
    EmployeeLeaveAllocation,
)

ZERO = Decimal("0.00")

# How the ledger rounds. Two decimal places, matching every NUMERIC(n,2) column
# it reads, so a half day is exact and no fold accumulates a rounding drift.
CENTS = Decimal("0.01")

# Leave requests whose days are marked but NOT funded from the leave pool. Kept
# in step with `leave.effects.BALANCE_DEDUCTING_TYPES` by construction: that set
# is every type EXCEPT unpaid, and this is unpaid.
NON_DEDUCTING_LEAVE_TYPES = (LeaveType.unpaid,)

# Leave request statuses that still hold a live claim on their days. A
# `cancellation_requested` leave is still approved until a manager rules on the
# withdrawal, so its days still count as taken - the same reading
# `leave/service.py` uses.
LIVE_LEAVE_STATUSES = (LeaveStatus.approved, LeaveStatus.cancellation_requested)


# ---------- month arithmetic ------------------------------------------------

def month_start(value: date) -> date:
    """The first day of `value`'s calendar month - the ledger's month key."""
    return date(value.year, value.month, 1)


def month_end(value: date) -> date:
    last = monthrange(value.year, value.month)[1]
    return date(value.year, value.month, last)


def next_month(value: date) -> date:
    """The first day of the month after `value`'s. Crosses the year correctly."""
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def previous_month(value: date) -> date:
    """The first day of the month before `value`'s. Crosses the year correctly."""
    if value.month == 1:
        return date(value.year - 1, 12, 1)
    return date(value.year, value.month - 1, 1)


def months_between(start: date, end: date) -> list[date]:
    """Every month key from `start`'s month through `end`'s month, inclusive.

    Empty when `end` precedes `start`. December to January is two entries, not a
    wrap to month 13, because the walk goes through `next_month`.
    """
    cursor, stop = month_start(start), month_start(end)
    out: list[date] = []
    while cursor <= stop:
        out.append(cursor)
        cursor = next_month(cursor)
    return out


def _q(value: Decimal) -> Decimal:
    return value.quantize(CENTS)


# The statuses that can carry funded leave. `half_day` is here because half of
# one may be leave - not because all of them are; `leave_days_for` decides, and
# answers 0 for a `half_day` row that never stated a fraction.
LEAVE_BEARING_STATUSES = (AttendanceStatus.leave, AttendanceStatus.half_day)


def leave_days_for(
    status: AttendanceStatus, leave_day_fraction: Decimal | None
) -> Decimal:
    """How many leave days one attendance row consumes. The single rule.

    Pure, so the half-day arithmetic is testable without a database, and shared
    so nothing counts leave a second way. `attendance_records` rows are the only
    thing that consumes leave (see the module header), and this is the only
    function that prices one.

    A STATED fraction always wins, including a stated 0 - a manager who says a
    half day cost no leave has said something, and it is not the same as saying
    nothing. NULL falls back to the pre-0083 rule, which is what keeps every
    historical row contributing exactly what it always did.

    Returns 0 for `present`, `absent`, `holiday`, `weekend` and `comp_off`: none
    of them is funded absence, and a stray fraction on one would be a data fault
    rather than a licence to charge the pool.
    """
    if status not in LEAVE_BEARING_STATUSES:
        return ZERO
    if leave_day_fraction is not None:
        return _q(Decimal(leave_day_fraction))
    return Decimal(1) if status == AttendanceStatus.leave else ZERO


# ---------- the answer ------------------------------------------------------

@dataclass(frozen=True)
class MonthBalance:
    """One employee's leave standing for one calendar month.

    Every term of the formula is reported, not just the total, because the PM
    correcting a balance and the employee querying theirs both need to see WHERE
    a figure came from - and because a card that shows only the total makes an
    accrual bug invisible.
    """

    employee_id: uuid.UUID
    month: date  # first day, so the month is unambiguous on the wire
    carry_forward: Decimal
    allocation: Decimal
    adjustment: Decimal
    consumed: Decimal
    # False for a month before this employee's ledger begins: they have no
    # allocation and no adjustment on or before it, so there is no balance to
    # state. Distinct from a real balance of zero.
    in_ledger: bool
    # The first month this employee has any ledger row for; None if they have
    # none at all.
    ledger_start: date | None

    @property
    def available(self) -> Decimal:
        """What the month had to spend, before its own leave was taken."""
        return _q(self.carry_forward + self.allocation + self.adjustment)

    @property
    def closing(self) -> Decimal:
        """The month's Available Leave - what carries into the next month."""
        return _q(self.available - self.consumed)


# ---------- inputs ----------------------------------------------------------

def _allocation_rows(
    db: Session, employee_id: uuid.UUID
) -> list[tuple[date, Decimal]]:
    """`(effective_from, monthly_days)` for one employee, oldest first."""
    rows = db.execute(
        select(
            EmployeeLeaveAllocation.effective_from,
            EmployeeLeaveAllocation.monthly_days,
        )
        .where(EmployeeLeaveAllocation.employee_id == employee_id)
        .order_by(EmployeeLeaveAllocation.effective_from)
    ).all()
    return [(eff, Decimal(days)) for eff, days in rows]


def allocation_in_force(
    rows: list[tuple[date, Decimal]], month: date
) -> Decimal:
    """The `Leave/month` in force for `month`, from pre-fetched rows.

    The newest row effective on or before the month - so a March rate change is
    invisible to January, and a rate set with a FUTURE effective month accrues
    nothing until that month arrives. Pure, so the effective-dating rule can be
    tested without a database.
    """
    key = month_start(month)
    current = ZERO
    for effective_from, monthly_days in rows:  # oldest first
        if effective_from > key:
            break
        current = monthly_days
    return current


def _adjustments_by_month(
    db: Session, employee_id: uuid.UUID, through: date
) -> dict[date, Decimal]:
    """Summed adjustment days per month, up to and including `through`'s month.

    Several corrections in one month add up rather than the last one winning:
    each is an event, and the ledger owes the employee all of them.
    """
    rows = db.execute(
        select(
            EmployeeLeaveAdjustment.effective_month,
            func.coalesce(func.sum(EmployeeLeaveAdjustment.days), 0),
        )
        .where(
            EmployeeLeaveAdjustment.employee_id == employee_id,
            EmployeeLeaveAdjustment.effective_month <= month_start(through),
        )
        .group_by(EmployeeLeaveAdjustment.effective_month)
    ).all()
    return {month: Decimal(total) for month, total in rows}


def _unpaid_dates(
    db: Session, employee_id: uuid.UUID, date_from: date, date_to: date
) -> set[date]:
    """Dates in the window covered by a live `unpaid` leave request.

    Ranges are compared with an overlap test rather than expanded day by day, so
    one query answers for the whole window however long the ranges are; the dates
    themselves are then enumerated only for the ranges that actually overlap.
    """
    rows = db.execute(
        select(LeaveRequest.start_date, LeaveRequest.end_date).where(
            LeaveRequest.employee_id == employee_id,
            LeaveRequest.leave_type.in_(NON_DEDUCTING_LEAVE_TYPES),
            LeaveRequest.status.in_(LIVE_LEAVE_STATUSES),
            LeaveRequest.start_date <= date_to,
            LeaveRequest.end_date >= date_from,
        )
    ).all()
    covered: set[date] = set()
    for start, end in rows:
        cursor = max(start, date_from)
        last = min(end, date_to)
        while cursor <= last:
            covered.add(cursor)
            cursor += timedelta(days=1)
    return covered


def _leave_days(
    db: Session, employee_id: uuid.UUID, date_from: date, date_to: date
) -> list[tuple[date, AttendanceStatus, Decimal | None]]:
    """Every date in the window that could carry leave, with what it cost.

    The fraction is fetched rather than assumed: pricing the day is
    `leave_days_for`'s job, and a row cannot be priced from its date alone.
    """
    return list(
        db.execute(
            select(
                AttendanceRecord.attendance_date,
                AttendanceRecord.status,
                AttendanceRecord.leave_day_fraction,
            ).where(
                AttendanceRecord.employee_id == employee_id,
                AttendanceRecord.status.in_(LEAVE_BEARING_STATUSES),
                AttendanceRecord.attendance_date >= date_from,
                AttendanceRecord.attendance_date <= date_to,
            )
        ).all()
    )


def _consumed_by_month(
    db: Session, employee_id: uuid.UUID, date_from: date, date_to: date
) -> dict[date, Decimal]:
    """Funded leave days consumed per month across the window.

    The SUM of what each marked day cost - not a COUNT of marked days. Those
    agree only while every leave is a whole day, which is exactly why a half-day
    leave used to cost nothing here. Days an unpaid request covers are dropped
    whatever fraction they carry.

    Two queries for the whole span rather than two per month.
    """
    marked = _leave_days(db, employee_id, date_from, date_to)
    if not marked:
        return {}
    unpaid = _unpaid_dates(db, employee_id, date_from, date_to)
    out: dict[date, Decimal] = {}
    for day, status, fraction in marked:
        if day in unpaid:
            continue
        cost = leave_days_for(status, fraction)
        if cost == ZERO:
            continue
        key = month_start(day)
        out[key] = out.get(key, ZERO) + cost
    return out


def ledger_start(db: Session, employee_id: uuid.UUID) -> date | None:
    """The first month this employee has any ledger row for, or None.

    Both tables are consulted: an employee may be given an allocation with no
    opening adjustment, or (as migration 0069 leaves everyone) an opening
    adjustment with no allocation yet.
    """
    earliest_allocation = db.execute(
        select(func.min(EmployeeLeaveAllocation.effective_from)).where(
            EmployeeLeaveAllocation.employee_id == employee_id
        )
    ).scalar_one()
    earliest_adjustment = db.execute(
        select(func.min(EmployeeLeaveAdjustment.effective_month)).where(
            EmployeeLeaveAdjustment.employee_id == employee_id
        )
    ).scalar_one()
    candidates = [d for d in (earliest_allocation, earliest_adjustment) if d]
    return min(candidates) if candidates else None


# ---------- the fold --------------------------------------------------------

def month_series(
    db: Session, employee_id: uuid.UUID, through: date
) -> list[MonthBalance]:
    """Every month of this employee's ledger, from its start through `through`.

    The whole history is folded because carry-forward makes each month depend on
    the one before it - August's closing balance IS September's opening one, so
    September cannot be answered on its own. Reading the series rather than
    recursing keeps it to a fixed number of queries no matter how many months
    have passed.

    Empty when the employee has no ledger, or when `through` falls before their
    ledger begins.
    """
    start = ledger_start(db, employee_id)
    if start is None:
        return []
    target = month_start(through)
    if target < start:
        return []

    allocation_rows = _allocation_rows(db, employee_id)
    adjustments = _adjustments_by_month(db, employee_id, target)
    consumed = _consumed_by_month(db, employee_id, start, month_end(target))

    series: list[MonthBalance] = []
    carry = ZERO
    for month in months_between(start, target):
        entry = MonthBalance(
            employee_id=employee_id,
            month=month,
            carry_forward=carry,
            allocation=_q(allocation_in_force(allocation_rows, month)),
            adjustment=_q(adjustments.get(month, ZERO)),
            consumed=_q(consumed.get(month, ZERO)),
            in_ledger=True,
            ledger_start=start,
        )
        series.append(entry)
        carry = entry.closing
    return series


def month_balance(
    db: Session, employee_id: uuid.UUID, month_of: date
) -> MonthBalance:
    """One employee's balance for the month containing `month_of`.

    The authoritative read. A month before the employee's ledger begins comes
    back with every term zero and `in_ledger=False`, so a caller can tell "no
    ledger yet" apart from "a balance of zero" and the UI need not guess.
    """
    series = month_series(db, employee_id, month_of)
    if series:
        return series[-1]
    return MonthBalance(
        employee_id=employee_id,
        month=month_start(month_of),
        carry_forward=ZERO,
        allocation=ZERO,
        adjustment=ZERO,
        consumed=ZERO,
        in_ledger=False,
        ledger_start=ledger_start(db, employee_id),
    )


def closing_balance(
    db: Session, employee_id: uuid.UUID, month_of: date
) -> Decimal:
    """The employee's Available Leave for that month. The number, on its own."""
    return month_balance(db, employee_id, month_of).closing


def spendable_on(
    db: Session, employee_id: uuid.UUID, day: date
) -> Decimal:
    """What the employee has available to spend on leave falling on `day`.

    The balance of `day`'s own month, which is the only figure that counts
    correctly when several future leaves are approved in turn: each month's
    closing already has every earlier month's consumption folded into it, so
    approving three days in October and then three in November weighs the second
    request against a balance the first has already reduced. Weighing both
    against "the balance today" would let the same days be granted twice.

    CLAMPED UP TO THE LEDGER'S START. A leave dated before the employee's ledger
    began is weighed against the ledger's FIRST month instead - the balance
    carried over from the pre-ledger era - because the ledger has nothing
    truthful to say about a month it did not cover, and answering zero would
    refuse a request the old stored balance would have allowed.

    An employee with no ledger at all has nothing to spend, which is exactly what
    the stored balance reported for an employee with no balance row.
    """
    start = ledger_start(db, employee_id)
    if start is None:
        return ZERO
    return month_balance(db, employee_id, max(month_start(day), start)).closing


# ---------- bulk read -------------------------------------------------------

def closing_balances(
    db: Session, employee_ids: list[uuid.UUID], month_of: date
) -> dict[uuid.UUID, MonthBalance]:
    """`month_balance` for several employees - what the PM's table needs.

    Loops rather than folding every employee in one pass: the fold is per
    employee by nature (each has their own ledger start and its own carry chain),
    and the manager's list is one page of employees at a time. Kept here so
    callers do not each grow their own loop.
    """
    return {
        employee_id: month_balance(db, employee_id, month_of)
        for employee_id in employee_ids
    }


def employees_with_ledger(db: Session, month_of: date) -> list[uuid.UUID]:
    """Every employee whose ledger has begun by `month_of` - the monthly
    notification's audience.

    Both tables, because an employee may have an allocation with no adjustment
    or (as migration 0069 leaves everyone) the reverse. Nobody outside this set
    has a balance to be told about.
    """
    key = month_start(month_of)
    from_allocations = select(EmployeeLeaveAllocation.employee_id).where(
        EmployeeLeaveAllocation.effective_from <= key
    )
    from_adjustments = select(EmployeeLeaveAdjustment.employee_id).where(
        EmployeeLeaveAdjustment.effective_month <= key
    )
    return list(db.execute(from_allocations.union(from_adjustments)).scalars())
