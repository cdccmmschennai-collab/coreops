"""Phase 10: what an APPROVED leave request does to the rest of CoreOps.

Everything a leave decision changes OUTSIDE `leave_requests` lives here, in one
module, so "approving leave marks the calendar and draws down the balance" is a
single readable rule rather than something spread across the service.

WHAT AN APPROVAL DOES
=====================
It writes one `attendance_records` row per WORKING day of the range, with
`status = leave` and NO check-in/check-out times.

That is the whole of it, and the deduction comes free with it.

PHASE 3: THE DEDUCTION IS THE DAY
=================================
This module used to do a second thing - subtract the day count from
`employee_leave_balances` and write a history row for the movement. It no longer
touches any balance, because there is no longer a stored one to touch:
`leave_balances/ledger.py` derives the balance, and counts these very rows as the
month's consumption. Marking the day IS the deduction.

Cancelling an approved leave therefore restores exactly what it took, without
any restoring code: `reverse_leave_approved` deletes the rows, and the ledger
stops counting them. Over-restoring is impossible for the same reason it always
was - only rows that still look exactly like an approval's are removed - and now
also because there is no figure to add back to. Cancelling twice credits nothing
twice: the second pass finds nothing left to delete.

`LeaveEffect.balance_before/after` survive as a read-only RECORD of the movement,
taken from the ledger either side of the write, for the audit row and the
employee's notification. Neither decides anything.

WHY attendance_records AND NOT A NEW TABLE
==========================================
`AttendanceStatus.leave` already exists, the employee calendar already paints it
amber, the day popover already lets an official status win over the biometric
label, and PM Records already shows it in its Status column. Approved leave
therefore needs no new state and no new visual language - it needs to arrive in
the table those screens already read. A parallel "leave days" table would be a
second source of truth for the same fact.

WHY IT NEVER OVERWRITES AN EXISTING RECORD
==========================================
A day that already has an official attendance decision keeps it (section 12H).
Approval SKIPS such a day rather than overwriting it, does not deduct balance for
it, and reports it back so the caller can tell the manager. `present` / `half_day`
days are rejected earlier still, by the service's own guard - you cannot be
granted leave for a day you are recorded as having worked.

WHY REMOVAL IS NARROW
=====================
Cancellation deletes ONLY a row that still looks exactly like the one an approval
writes: status `leave`, both boundary times NULL, on a working day of the range.
The moment a PM edits that day - adds a time, changes the status - it stops
matching and is left alone. CoreOps never deletes a human decision here.

BIOMETRIC EVIDENCE IS NOT TOUCHED
=================================
Nothing in this module reads or writes `biometric_punches`, and no punch is
rewritten, hidden or reinterpreted. An approved leave day with punches on it
keeps every punch, and the biometric `classification` stays exactly what the
device supports - the leave row sits BESIDE that evidence, as the official
decision, which is the same separation `_review_row` already maintains. Resolving
the resulting disagreement is the later leave/biometric conflict phase; this
module only makes sure the two facts can coexist without either being corrupted.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.calendar.working_days import (
    is_working_day,
    load_calendar_overrides,
)
from app.modules.leave.models import LeaveRequest, LeaveType
from app.modules.leave_balances import ledger
from app.modules.users.models import User

# Leave types that draw down `employee_leave_balances.available_leave`.
#
# `unpaid` is deliberately absent: unpaid leave is BY DEFINITION not taken from
# the leave pool, so deducting it would both misstate the balance and make the
# insufficient-balance guard reject the one request that exists precisely for the
# case where there is no balance left. An unpaid day is still marked Leave on the
# calendar - it is real absence, just not funded absence.
BALANCE_DEDUCTING_TYPES = frozenset(
    {
        LeaveType.casual,
        LeaveType.sick,
        LeaveType.annual,
        LeaveType.comp_off,
        LeaveType.other,
    }
)

# A leave range is a handful of days. This only exists so a malformed or hostile
# range cannot turn one approval into an unbounded day-by-day loop.
MAX_LEAVE_RANGE_DAYS = 366


def deducts_balance(leave_type: LeaveType) -> bool:
    """Whether this leave type is drawn from `available_leave`."""
    return leave_type in BALANCE_DEDUCTING_TYPES


@dataclass
class LeaveEffect:
    """What an approval (or its reversal) actually changed.

    Returned rather than logged so the caller owns the messaging, and so tests
    can assert on the outcome instead of re-querying three tables.
    """

    # Days marked Leave (on apply) or un-marked (on reverse).
    days: list[date] = field(default_factory=list)
    # Days skipped because they already carried an official attendance decision.
    skipped: list[date] = field(default_factory=list)
    balance_before: Decimal | None = None
    balance_after: Decimal | None = None

    @property
    def day_count(self) -> int:
        return len(self.days)

    @property
    def deducted(self) -> Decimal:
        """Absolute balance movement, or 0 when this type does not deduct."""
        if self.balance_before is None or self.balance_after is None:
            return Decimal("0")
        return abs(self.balance_after - self.balance_before)


# ---------- day resolution --------------------------------------------------

def _range_days(start_date: date, end_date: date) -> list[date]:
    span = (end_date - start_date).days
    if span < 0:
        return []
    if span + 1 > MAX_LEAVE_RANGE_DAYS:
        span = MAX_LEAVE_RANGE_DAYS - 1
    return [start_date + timedelta(days=i) for i in range(span + 1)]


def leave_working_days(db: Session, start_date: date, end_date: date) -> list[date]:
    """The days of a leave range that actually cost the employee anything.

    Mon-Fri minus company holidays, plus any declared `working_day` override -
    resolved by `calendar/working_days.py`, which is CoreOps' existing and
    already-tested answer to "is the office open". A Friday-to-Monday leave is
    two days, not four, and a leave range that lands entirely on a public holiday
    is zero.

    One query for the whole range, not one per day.
    """
    days = _range_days(start_date, end_date)
    if not days:
        return []
    non_working, working_overrides = load_calendar_overrides(db, days[0], days[-1])
    return [
        d
        for d in days
        if is_working_day(d, non_working=non_working, working_overrides=working_overrides)
    ]


def _existing_records(
    db: Session, employee_id: uuid.UUID, days: list[date]
) -> dict[date, AttendanceRecord]:
    if not days:
        return {}
    rows = db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.attendance_date.in_(days),
        )
    ).scalars()
    return {r.attendance_date: r for r in rows}


def plan_leave_days(
    db: Session, req: LeaveRequest
) -> tuple[list[date], list[date]]:
    """`(days_to_mark, days_already_decided)` for this request, deciding nothing.

    Pure read. Used BEFORE approval to size the balance check against exactly the
    days that will really be marked, so the check and the effect can never
    disagree about how many days a request costs.
    """
    working = leave_working_days(db, req.start_date, req.end_date)
    existing = _existing_records(db, req.employee_id, working)
    to_mark = [d for d in working if d not in existing]
    skipped = [d for d in working if d in existing]
    return to_mark, skipped


# ---------- balance ---------------------------------------------------------

def _balance_on(db: Session, employee_id: uuid.UUID, day: date) -> Decimal:
    """The employee's leave balance for `day`'s month, from the ledger.

    READ-ONLY, and used only to RECORD what a decision did - never to decide
    anything. The figure goes into the audit row and into the sentence the
    employee's notification ends with ("3 days deducted ... (10 to 7)"), both of
    which would otherwise lose the movement now that nothing stores it.

    The same `spendable_on` the approval guard weighed the request against, so
    the "before" in the notification is the very number the decision was made on
    rather than a second opinion taken from a different month.

    Phase 3 removed the stored counter this module used to move. Consumption is
    the `leave` attendance rows written below, and the ledger counts them - so
    the deduction happens by writing the day, not by adjusting a number, and the
    two can no longer disagree.
    """
    return ledger.spendable_on(db, employee_id, day)


def _long_date(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def _period(req: LeaveRequest) -> str:
    start = _long_date(req.start_date)
    if req.start_date == req.end_date:
        return start
    return f"{start} - {_long_date(req.end_date)}"


# ---------- apply / reverse -------------------------------------------------

def apply_leave_approved(
    db: Session, actor: User, req: LeaveRequest
) -> LeaveEffect:
    """Mark the calendar and draw down the balance for a just-approved request.

    FLUSHES, never commits: the attendance rows, the balance movement and the
    request's own `status = approved` all land in the caller's single
    transaction, so there is no window in which a leave is approved but its days
    are not marked.
    """
    to_mark, skipped = plan_leave_days(db, req)
    effect = LeaveEffect(days=list(to_mark), skipped=list(skipped))

    # Read before the days are written, so the pair recorded below is the real
    # movement. Only for types that draw on the pool - an unpaid approval moves
    # nothing and must not claim to.
    deducting = deducts_balance(req.leave_type)
    charged_month_day = to_mark[-1] if to_mark else None
    before = (
        _balance_on(db, req.employee_id, charged_month_day)
        if (charged_month_day is not None and deducting)
        else None
    )

    for day in to_mark:
        record = AttendanceRecord(
            employee_id=req.employee_id,
            attendance_date=day,
            status=AttendanceStatus.leave,
            # Never a fabricated time. An approved leave day has no IN and no
            # OUT, which is exactly what the calendar popover renders as "-".
            check_in_at=None,
            check_out_at=None,
            total_minutes=0,
            overtime_minutes=0,
            note=f"Approved {req.leave_type.value} leave ({_period(req)}).",
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(record)
        db.flush()
        # Audited exactly like a PM-entered day: one row per employee-day, in the
        # attendance module's own vocabulary, so "who decided this day meant
        # leave" is answerable from the same audit filter as every other
        # attendance decision.
        record_audit(
            db,
            action=AuditAction.ATTENDANCE_RECORD_CREATE,
            actor=actor,
            entity_type=EntityType.ATTENDANCE_RECORD,
            entity_id=record.id,
            details={
                "employee_id": str(req.employee_id),
                "attendance_date": day.isoformat(),
                "status": AttendanceStatus.leave.value,
                "source": "leave_approval",
                "leave_request_id": str(req.id),
            },
        )

    if before is not None:
        # The days are already flushed, so the ledger now counts them: the
        # deduction IS the rows above. Nothing here writes a balance.
        effect.balance_before = before
        effect.balance_after = _balance_on(db, req.employee_id, charged_month_day)

    return effect


def reverse_leave_approved(
    db: Session, actor: User, req: LeaveRequest
) -> LeaveEffect:
    """Undo `apply_leave_approved` when an approved leave is cancelled.

    Removes only rows that still look exactly like the ones an approval writes
    (status `leave`, no times, on a working day of the range) and restores the
    balance by the number of rows ACTUALLY removed. That symmetry is what makes
    over-restoring impossible: a day the PM has since edited is neither deleted
    nor refunded, and a leave approved before Phase 10 - which therefore has no
    rows at all - restores nothing rather than inventing a credit.

    FLUSHES, never commits.
    """
    working = leave_working_days(db, req.start_date, req.end_date)
    existing = _existing_records(db, req.employee_id, working)

    deducting = deducts_balance(req.leave_type)
    # Read against the same month the approval charged - the last working day of
    # the range - so the restore is reported in the month it actually happens in.
    charged_month_day = working[-1] if working else None
    before = (
        _balance_on(db, req.employee_id, charged_month_day)
        if (charged_month_day is not None and deducting)
        else None
    )

    removed: list[date] = []
    kept: list[date] = []
    for day in working:
        record = existing.get(day)
        if record is None:
            continue
        if (
            record.status == AttendanceStatus.leave
            and record.check_in_at is None
            and record.check_out_at is None
        ):
            record_audit(
                db,
                action=AuditAction.ATTENDANCE_RECORD_DELETE,
                actor=actor,
                entity_type=EntityType.ATTENDANCE_RECORD,
                entity_id=record.id,
                details={
                    "employee_id": str(req.employee_id),
                    "attendance_date": day.isoformat(),
                    "status": AttendanceStatus.leave.value,
                    "source": "leave_cancellation",
                    "leave_request_id": str(req.id),
                },
            )
            db.delete(record)
            removed.append(day)
        else:
            # A human has since ruled on this day. Their decision stands.
            kept.append(day)

    db.flush()
    effect = LeaveEffect(days=removed, skipped=kept)

    if removed and before is not None:
        # The rows are gone, so the ledger has already stopped counting them.
        # The restore is exact BY CONSTRUCTION - it is the number of rows
        # actually deleted - and cancelling twice cannot restore twice, because
        # the second pass finds nothing left to delete.
        effect.balance_before = before
        effect.balance_after = _balance_on(db, req.employee_id, charged_month_day)

    return effect
