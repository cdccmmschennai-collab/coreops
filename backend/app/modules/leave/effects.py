"""Phase 10: what an APPROVED leave request does to the rest of CoreOps.

Everything a leave decision changes OUTSIDE `leave_requests` lives here, in one
module, so "approving leave marks the calendar and draws down the balance" is a
single readable rule rather than something spread across the service.

WHAT AN APPROVAL DOES
=====================
1. Writes one `attendance_records` row per WORKING day of the range, with
   `status = leave` and NO check-in/check-out times.
2. Deducts that same number of days from `employee_leave_balances`, and writes
   the immutable `EmployeeLeaveBalanceHistory` row the balance module already
   requires of every mutation.

Cancelling an approved leave reverses both, and reversal is defined so it can
never over-restore: the balance goes back up by exactly the number of attendance
rows actually removed, so a day the PM has since re-decided is neither removed
nor refunded.

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
from app.modules.leave_balances.models import (
    EmployeeLeaveBalance,
    EmployeeLeaveBalanceHistory,
)
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

def _locked_balance(
    db: Session, employee_id: uuid.UUID
) -> EmployeeLeaveBalance | None:
    """The balance row under `SELECT ... FOR UPDATE`.

    Two leave requests for the same employee approved concurrently lock the same
    balance row here, so the second reads the value the first wrote instead of
    both deducting from the same starting figure.
    """
    return db.execute(
        select(EmployeeLeaveBalance)
        .where(EmployeeLeaveBalance.employee_id == employee_id)
        .with_for_update()
    ).scalar_one_or_none()


def available_balance(db: Session, employee_id: uuid.UUID) -> Decimal:
    """Current available leave. A missing row reads as zero, exactly as the
    leave-balance module's own read endpoint reports it."""
    bal = db.execute(
        select(EmployeeLeaveBalance).where(
            EmployeeLeaveBalance.employee_id == employee_id
        )
    ).scalar_one_or_none()
    return bal.available_leave if bal else Decimal("0")


def _move_balance(
    db: Session,
    *,
    actor: User,
    employee_id: uuid.UUID,
    delta: Decimal,
    reason: str,
) -> tuple[Decimal, Decimal]:
    """Apply `delta` to the balance and write the mandatory history row.

    Goes through the same two tables `leave_balances.set_balance` writes, so the
    manager's Leave Balance tab and its history show an automatic movement in
    exactly the same shape as a manual edit. FLUSHES only - the caller commits,
    so the balance moves atomically with the status change that caused it.
    """
    bal = _locked_balance(db, employee_id)
    old_value = bal.available_leave if bal else None
    base = old_value if old_value is not None else Decimal("0")
    new_value = (base + delta).quantize(Decimal("0.01"))

    if bal is None:
        bal = EmployeeLeaveBalance(employee_id=employee_id, available_leave=new_value)
        db.add(bal)
    else:
        bal.available_leave = new_value
        db.add(bal)

    db.add(
        EmployeeLeaveBalanceHistory(
            employee_id=employee_id,
            old_balance=old_value,
            new_balance=new_value,
            reason=reason,
            updated_by=actor.id,
        )
    )
    db.flush()
    return base, new_value


def _long_date(value: date) -> str:
    return f"{value.day} {value:%B %Y}"


def _period(req: LeaveRequest) -> str:
    start = _long_date(req.start_date)
    if req.start_date == req.end_date:
        return start
    return f"{start} - {_long_date(req.end_date)}"


def _days_word(count: int) -> str:
    return "day" if count == 1 else "days"


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

    if to_mark and deducts_balance(req.leave_type):
        before, after = _move_balance(
            db,
            actor=actor,
            employee_id=req.employee_id,
            delta=-Decimal(len(to_mark)),
            reason=(
                f"Leave approved: {len(to_mark)} {_days_word(len(to_mark))} "
                f"({req.leave_type.value}, {_period(req)})"
            ),
        )
        effect.balance_before, effect.balance_after = before, after

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

    if removed and deducts_balance(req.leave_type):
        before, after = _move_balance(
            db,
            actor=actor,
            employee_id=req.employee_id,
            delta=Decimal(len(removed)),
            reason=(
                f"Approved leave cancelled: {len(removed)} "
                f"{_days_word(len(removed))} restored "
                f"({req.leave_type.value}, {_period(req)})"
            ),
        )
        effect.balance_before, effect.balance_after = before, after

    return effect
