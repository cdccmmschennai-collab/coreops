"""The monthly permission allowance, and the one place it is computed.

THE RULE
========
Every employee gets 4 hours of permission per CALENDAR MONTH. What is left is

    remaining = 4 - SUM(duration_hours of that month's APPROVED requests)

and that is the whole of it. There is no stored counter anywhere, which is what
makes the Phase 11 rules true by construction rather than by maintenance:

  pending      does not consume - only `approved` rows are summed
  rejected     does not consume - same reason
  withdrawal   asking to cancel an approved permission does NOT give the hours
   requested   back: `cancellation_requested` is summed exactly as `approved`
               is, so the allowance moves only when a reviewer actually rules
  cancelled    restores exactly what it took - the row stops being summed, so
               there is no figure to adjust and no way to over-restore
  cancel twice cannot restore twice - the second attempt is refused by the status
               guard, and even if it were not, summing is idempotent
  month end    nothing carries forward - each month sums only its own rows, so
               an unused August hour cannot become a fifth September hour

The other side of "nothing carries forward" is that a finished month has nothing
left to spend, so a NEW request cannot be filed against it - `month_has_closed`
below states that rule and `service._assert_month_open` enforces it. Reading a
closed month is untouched: its figures are still derived the same way and its
history is still fully visible.

WHICH MONTH A REQUEST BELONGS TO
================================
The month of `permission_date` - the business day the employee is actually absent
- never the month the row was created in and never a UTC instant. A request filed
at 00:30 IST on 1 September for 31 August is August's, because the absence is
August's. `permission_date` is a plain DATE, so this is timezone-proof by
construction; the only place a clock is consulted is "which month is NOW", and
that reads the Chennai business date (see `service._today`).

CONCURRENCY
===========
`lock_month` takes `SELECT ... FOR UPDATE` over EVERY one of the employee's
requests in the month - pending ones included - before any approval sums them.
Any second approval in that month necessarily targets one of those rows, so it
blocks and then re-reads the total the winner wrote. Locking the whole month
rather than just the target row is what closes the real hole: two DIFFERENT
pending requests approved at the same instant would otherwise both read the same
`remaining` and both be allowed. Rows are locked in `id` order by both writers,
so the pattern cannot deadlock.
"""
from __future__ import annotations

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.permissions.models import PermissionRequest, PermissionStatus

# The company allowance. One number, one place.
MONTHLY_ALLOWANCE_HOURS = 4

# The only durations a permission may have. No 30 minutes, no custom value, no
# decimals - mirrored by the DB check constraint and the request schema.
ALLOWED_DURATIONS = (1, 2)

# Statuses that still hold a claim on the employee's month. A pending request is
# NOT one of them for balance purposes (it consumes nothing), but it is for the
# duplicate-request guard - see `service._assert_no_active_request`.
#
# `cancellation_requested` IS one of them (Phase 4E). An approved permission the
# employee has merely ASKED to withdraw has not been withdrawn: it stands until a
# reviewer rules, so its hours stay spent. Leaving it out would let anyone free
# their allowance by requesting a cancellation nobody has approved, and would
# make a rejected withdrawal silently re-spend hours the month had already given
# back - the same reason `leave` keeps the state in its active set.
CONSUMING_STATUSES = (
    PermissionStatus.approved,
    PermissionStatus.cancellation_requested,
)


def month_bounds(value: date) -> tuple[date, date]:
    """The first and last day of `value`'s calendar month."""
    last = monthrange(value.year, value.month)[1]
    return date(value.year, value.month, 1), date(value.year, value.month, last)


def month_has_closed(value: date, today: date) -> bool:
    """Whether `value` falls in a calendar month EARLIER than `today`'s.

    Pure, so the rule can be reasoned about without a clock or a database. The
    comparison is month-to-month, not date-to-date: 3 August is not closed on
    20 August, because the month it belongs to is still running, but every August
    date is closed on 1 September.

    A month's permission allowance exists to be spent inside that month, and it
    does not carry forward - so once the month is over there is nothing left to
    ask for. `today` must be the Chennai business date (see `service._today`), or
    the boundary would move for anyone filing just after midnight IST.
    """
    return (value.year, value.month) < (today.year, today.month)


@dataclass(frozen=True)
class PermissionBalance:
    """One employee's permission standing for one calendar month."""

    employee_id: uuid.UUID
    month: date  # first day of the month, so the month is unambiguous on the wire
    allowance_hours: int
    approved_hours: int
    # Whether this month is the one running NOW, on the business calendar.
    is_current_month: bool = True
    # Whether a NEW request may be filed against this month. A closed month is
    # still fully readable - the figures above stay true - it just cannot be
    # spent from any more.
    requests_allowed: bool = True

    @property
    def remaining_hours(self) -> int:
        # Clamped at zero so a balance edited into an odd state by hand can never
        # be reported as a negative allowance to the UI. The approval guard is
        # what actually prevents overspending.
        return max(0, self.allowance_hours - self.approved_hours)


def approved_hours(db: Session, employee_id: uuid.UUID, month_of: date) -> int:
    """Approved permission hours the employee has used in `month_of`'s month."""
    start, end = month_bounds(month_of)
    total = db.execute(
        select(func.coalesce(func.sum(PermissionRequest.duration_hours), 0)).where(
            PermissionRequest.employee_id == employee_id,
            PermissionRequest.status.in_(CONSUMING_STATUSES),
            PermissionRequest.permission_date >= start,
            PermissionRequest.permission_date <= end,
        )
    ).scalar_one()
    return int(total or 0)


def balance_for(
    db: Session, employee_id: uuid.UUID, month_of: date, today: date | None = None
) -> PermissionBalance:
    """The employee's permission balance for the month containing `month_of`.

    `today` (the Chennai business date) decides only the two reporting flags; the
    hours themselves are the same whichever month is asked about, because each
    month sums its own rows and nothing carries forward. Passing it is how the
    caller says "and tell me whether this month can still be spent from" - the
    refusal itself lives in `service.create_permission_request`, not here.
    """
    start, _end = month_bounds(month_of)
    closed = month_has_closed(start, today) if today is not None else False
    return PermissionBalance(
        employee_id=employee_id,
        month=start,
        allowance_hours=MONTHLY_ALLOWANCE_HOURS,
        approved_hours=approved_hours(db, employee_id, month_of),
        is_current_month=(
            today is not None and (start.year, start.month) == (today.year, today.month)
        ),
        # A future month is not closed: filing ahead has always been allowed, and
        # Phase 3 adds no future-month policy.
        requests_allowed=not closed,
    )


def lock_month(db: Session, employee_id: uuid.UUID, month_of: date) -> None:
    """Lock every request this employee has in `month_of`'s month.

    Held until the caller commits. Must be taken BEFORE the balance is summed on
    any path that changes an approved total, so concurrent decisions serialise
    instead of both reading the same remaining figure.
    """
    start, end = month_bounds(month_of)
    db.execute(
        select(PermissionRequest.id)
        .where(
            PermissionRequest.employee_id == employee_id,
            PermissionRequest.permission_date >= start,
            PermissionRequest.permission_date <= end,
        )
        # Deterministic order, so two writers touching the same month acquire the
        # same rows in the same sequence and cannot deadlock each other.
        .order_by(PermissionRequest.id)
        .with_for_update()
    ).all()


def hours_word(hours: int) -> str:
    return "hour" if hours == 1 else "hours"


def format_hours(hours: int) -> str:
    """`4h` - the form the KPI and the notifications both use."""
    return f"{hours}h"
