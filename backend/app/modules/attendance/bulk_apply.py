"""Bulk attendance apply (Phase 4): one status over employees x dates.

    POST /attendance/bulk-apply   dry_run=true   preview, writes nothing
                                  dry_run=false  apply, partial success

Every (employee, date) pair is judged on its own and gets exactly one outcome:

    created     no record existed; one is written
    updated     the record's status changes
    unchanged   the record already has this status - nothing is written
    protected   the record was written by an approved leave and is still the
                row that leave's cancellation would remove, or is the day off an
                approved comp off request wrote - never touched
    rejected    the pair is invalid; `reason_code` says why

Nothing is skipped silently: a non-working day, a duplicate pair, a missing
reason are all `rejected` with their reason, so the caller can show every one.

WHAT A BULK WRITE TOUCHES
=========================
Status, the action's note and the leave charge that follows from the status
(`service._settle_leave_fraction`, the same rule the sheet uses). Check-in /
check-out times and permission data are NEVER written: a new row has no times,
an existing row keeps its own.

WHAT IT DOES NOT CHANGE
=======================
Automatic reports are still produced only by the scheduled 01:00 sweep, on its
existing window. The only report-side call is the same in-transaction
`_reconcile_auto_leave_reports` every attendance write already makes - it can
unlock a report a changed day no longer backs, it never generates one.

CONCURRENCY
===========
The apply re-reads every existing row under `FOR UPDATE` (ordered by id, so two
overlapping actions lock in the same order), and each write runs in its own
SAVEPOINT. A row inserted by somebody else between the read and the write hits
the (employee, date) unique constraint; only that pair is rolled back and
reported `rejected / concurrent_change`. A repeated submission finds every row
already in the target state and reports `unchanged`, writing nothing.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.attendance import service
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.attendance.schemas import AttendanceBulkApply
from app.modules.audit.constants import AuditAction
from app.modules.calendar.working_days import is_working_day, load_calendar_overrides
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.leave.effects import (
    attendance_marking,
    converted_rows,
    is_approval_row,
)
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave_balances.ledger import LIVE_LEAVE_STATUSES
from app.modules.users.models import User

# Statuses that block a leave request for the day (`leave.service._WORKED_ATTENDANCE`).
_WORKED = (AttendanceStatus.present, AttendanceStatus.half_day)

# A summary notification names at most this many days, then "and N more".
_NOTIFY_MAX_DAYS = 10

_REJECT_MESSAGES = {
    "duplicate_in_request": "This employee-date appears more than once in the request.",
    "employee_not_found": "Employee not found.",
    "before_joining": "The date is before the employee's date of joining.",
    "employee_exited": "The employee has exited; only past days can be corrected.",
    "non_working_day": (
        "Not a working day - skipped. Set include_non_working to apply it."
    ),
    "reason_required": "A reason is required when changing attendance for a past date.",
    "concurrent_change": (
        "This day was changed by someone else while the action ran. Try again."
    ),
}


@dataclass
class _Item:
    employee_id: uuid.UUID
    attendance_date: date
    outcome: str = "rejected"
    reason_code: str | None = None
    message: str | None = None
    record: AttendanceRecord | None = None
    previous_status: AttendanceStatus | None = None
    status: AttendanceStatus | None = None
    warnings: list[dict] = field(default_factory=list)

    def reject(self, code: str) -> None:
        self.outcome, self.reason_code = "rejected", code
        self.message = _REJECT_MESSAGES[code]


def _load_existing(
    db: Session, employee_ids: list[uuid.UUID], dates: list[date], *, lock: bool
) -> dict[tuple[uuid.UUID, date], AttendanceRecord]:
    """Every existing row on the pairs, keyed by (employee, date). Locked on apply."""
    stmt = (
        select(AttendanceRecord)
        .where(
            AttendanceRecord.employee_id.in_(employee_ids),
            AttendanceRecord.attendance_date.in_(dates),
        )
        .order_by(AttendanceRecord.id)
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return {
        (r.employee_id, r.attendance_date): r for r in db.execute(stmt).scalars().all()
    }


def _leave_requests(
    db: Session,
    employee_ids: list[uuid.UUID],
    first: date,
    last: date,
    statuses: tuple[LeaveStatus, ...],
) -> dict[uuid.UUID, list[LeaveRequest]]:
    rows = db.execute(
        select(LeaveRequest).where(
            LeaveRequest.employee_id.in_(employee_ids),
            LeaveRequest.status.in_(statuses),
            LeaveRequest.start_date <= last,
            LeaveRequest.end_date >= first,
        )
    ).scalars()
    out: dict[uuid.UUID, list[LeaveRequest]] = defaultdict(list)
    for req in rows:
        out[req.employee_id].append(req)
    return out


def _is_protected(
    record: AttendanceRecord,
    live: list[LeaveRequest],
    *,
    working: bool,
    converted: set[uuid.UUID],
) -> bool:
    """Whether a live leave approval's cancellation would still remove this row.

    The exact rule `leave.effects.reverse_leave_approved` deletes by: a working
    day of the request's range, and a row still shaped like the approval wrote
    it (`is_approval_row`). A row a PM has since edited fails the shape test
    and is an ordinary record again.

    Or would still RESTORE it: a Present day a live half-day leave converted
    (`converted`, from `effects.converted_rows`) and still `half_day`. It keeps
    its times, so the shape test cannot see it.
    """
    if not working:
        return False
    if record.id in converted and record.status == AttendanceStatus.half_day:
        return True
    for req in live:
        if req.start_date <= record.attendance_date <= req.end_date:
            status, fraction = attendance_marking(req)
            if is_approval_row(record, status, fraction):
                return True
    return False


def bulk_apply(db: Session, actor: User, data: AttendanceBulkApply) -> dict:
    today = service._business_today()
    note = service._clean_note(data.note)
    target = data.status

    employee_ids = list(dict.fromkeys(data.employee_ids))
    dates = sorted(set(data.dates))
    first, last = dates[0], dates[-1]

    employees = {
        e.id: e
        for e in db.execute(select(Employee).where(Employee.id.in_(employee_ids)))
        .scalars()
        .all()
    }
    non_working, working_overrides = load_calendar_overrides(db, first, last)
    existing = _load_existing(db, employee_ids, dates, lock=not data.dry_run)
    live = _leave_requests(db, employee_ids, first, last, LIVE_LEAVE_STATUSES)
    pending = (
        _leave_requests(db, employee_ids, first, last, (LeaveStatus.pending,))
        if target in _WORKED
        else {}
    )
    converted = set(
        converted_rows(
            db,
            [r.id for reqs in live.values() for r in reqs if r.half_day_period is not None],
        )
    )

    items: list[_Item] = []
    seen: set[tuple[uuid.UUID, date]] = set()
    # Employees outer, dates inner, in the order the caller sent them - so the
    # results read in the order the request was written.
    for employee_id in data.employee_ids:
        for day in data.dates:
            item = _Item(employee_id=employee_id, attendance_date=day)
            items.append(item)
            pair = (employee_id, day)
            if pair in seen:
                item.reject("duplicate_in_request")
                continue
            seen.add(pair)
            _evaluate(
                item,
                employee=employees.get(employee_id),
                record=existing.get(pair),
                target=target,
                note=note,
                today=today,
                working=is_working_day(
                    day, non_working=non_working, working_overrides=working_overrides
                ),
                include_non_working=data.include_non_working,
                live=live.get(employee_id, []),
                pending=pending.get(employee_id, []),
                converted=converted,
            )

    bulk_action_id = None
    if not data.dry_run:
        bulk_action_id = uuid.uuid4()
        _apply(db, actor, items, target=target, note=note, bulk_action_id=bulk_action_id)

    return _response(items, employees, data, bulk_action_id)


def _evaluate(
    item: _Item,
    *,
    employee: Employee | None,
    record: AttendanceRecord | None,
    target: AttendanceStatus,
    note: str | None,
    today: date,
    working: bool,
    include_non_working: bool,
    live: list[LeaveRequest],
    pending: list[LeaveRequest],
    converted: set[uuid.UUID],
) -> None:
    """Decide one pair's outcome. Reads only; the same verdict for preview and apply."""
    day = item.attendance_date
    if employee is None or employee.deleted_at is not None:
        return item.reject("employee_not_found")
    if employee.date_of_joining is not None and day < employee.date_of_joining:
        return item.reject("before_joining")
    if employee.status == EmployeeStatus.exited and day >= today:
        return item.reject("employee_exited")
    if not working and not include_non_working:
        return item.reject("non_working_day")

    if record is not None:
        item.record = record
        item.previous_status = record.status
        item.status = record.status
        if (
            record.comp_off_request_id is not None
            and record.status == AttendanceStatus.comp_off
        ):
            # The day off an approved comp off request wrote (migration 0088).
            # An approved request is final, so the row is protected for as long
            # as it is still the comp off it wrote.
            item.outcome, item.reason_code = "protected", "comp_off_approval"
            item.message = (
                "Written by an approved comp off request. Change it from the "
                "attendance record itself, not here."
            )
            return None
        if _is_protected(record, live, working=working, converted=converted):
            item.outcome, item.reason_code = "protected", "leave_approval"
            item.message = (
                "Written by an approved leave request. Change it through the "
                "leave request (cancel or edit), not here."
            )
            return None
        if record.status == target:
            item.outcome, item.reason_code = "unchanged", "already_set"
            item.message = "Already has this status."
            return None

    # From here on the day WOULD change, so the past-date reason rule applies.
    if day < today and note is None:
        return item.reject("reason_required")

    item.outcome = "created" if record is None else "updated"
    item.status = target
    if target in _WORKED and any(r.start_date <= day <= r.end_date for r in pending):
        item.warnings.append(
            {
                "code": "pending_leave_request",
                "message": (
                    "A pending leave request covers this day. Marking it "
                    f"{service._STATUS_LABELS[target]} will block that request's approval."
                ),
            }
        )
    if (
        record is not None
        and (record.check_in_at is not None or record.check_out_at is not None)
        and target not in _WORKED
    ):
        item.warnings.append(
            {
                "code": "existing_times_kept",
                "message": "The recorded check-in/check-out times are kept unchanged.",
            }
        )
    return None


def _apply(
    db: Session,
    actor: User,
    items: list[_Item],
    *,
    target: AttendanceStatus,
    note: str | None,
    bulk_action_id: uuid.UUID,
) -> None:
    written: list[tuple[AttendanceRecord, AttendanceStatus | None]] = []
    for item in items:
        if item.outcome not in ("created", "updated"):
            continue
        try:
            with db.begin_nested():
                record = _write(
                    db, actor, item, target=target, note=note,
                    bulk_action_id=bulk_action_id,
                )
        except IntegrityError:
            # Someone else inserted this employee-day after it was read. Only
            # this pair's savepoint is undone; the rest of the action stands.
            item.record, item.status = None, None
            item.reject("concurrent_change")
            continue
        item.record = record
        written.append((record, item.previous_status))

    # Same in-transaction reconciliation every attendance write makes. It never
    # generates a report; the 01:00 sweep remains the only generator.
    service._reconcile_auto_leave_reports(db, [record for record, _ in written])
    db.commit()
    _notify_summary(db, actor, written)


def _write(
    db: Session,
    actor: User,
    item: _Item,
    *,
    target: AttendanceStatus,
    note: str | None,
    bulk_action_id: uuid.UUID,
) -> AttendanceRecord:
    """Write one pair inside the caller's SAVEPOINT. Status, note, leave charge."""
    record = item.record
    if record is None:
        record = AttendanceRecord(
            employee_id=item.employee_id,
            attendance_date=item.attendance_date,
            status=target,
            check_in_at=None,
            check_out_at=None,
            total_minutes=0,
            overtime_minutes=0,
            note=note,
            leave_day_fraction=service._validated_leave_fraction(None, target),
            created_by=actor.id,
            updated_by=actor.id,
        )
        db.add(record)
        db.flush()
        service._audit_record(
            db,
            actor=actor,
            action=AuditAction.ATTENDANCE_RECORD_CREATE,
            record=record,
            note=note,
            previous_status=None,
            source="bulk",
            extra={"bulk_action_id": str(bulk_action_id)},
        )
        return record

    previous = service._snapshot(record)
    record.status = target
    # Times are never touched, so neither are the minutes derived from them.
    service._settle_leave_fraction(record, item.previous_status)
    if note is not None:
        record.note = note
    record.updated_by = actor.id
    db.flush()
    service._audit_record(
        db,
        actor=actor,
        action=AuditAction.ATTENDANCE_RECORD_UPDATE,
        record=record,
        note=note,
        previous_status=item.previous_status,
        previous=previous,
        source="bulk",
        extra={"bulk_action_id": str(bulk_action_id)},
    )
    return record


def _notify_summary(
    db: Session,
    actor: User,
    written: list[tuple[AttendanceRecord, AttendanceStatus | None]],
) -> None:
    """ONE notification per employee for the whole action.

    The same rule as `service._notify_rulings` decides which days are news - set
    INTO or changed OUT OF a ruling status (`present` stays silent) - and the
    same after-commit, swallow-failure contract applies. Self-edits are skipped.
    """
    from app.modules.notifications.service import create_notification

    actor_employee = service._current_employee(db, actor)
    actor_employee_id = actor_employee.id if actor_employee is not None else None
    by = actor_employee.full_name if actor_employee is not None else "your manager"

    by_employee: dict[
        uuid.UUID, list[tuple[AttendanceRecord, AttendanceStatus | None]]
    ] = defaultdict(list)
    for record, previous_status in written:
        if record.employee_id == actor_employee_id:
            continue
        if (
            record.status in service._NOTIFIED_STATUSES
            or previous_status in service._NOTIFIED_STATUSES
        ):
            by_employee[record.employee_id].append((record, previous_status))

    for employee_id, days in by_employee.items():
        employee = db.get(Employee, employee_id)
        if employee is None or employee.user_id is None:
            continue
        days.sort(key=lambda pair: pair[0].attendance_date)
        changed = any(previous is not None for _, previous in days)
        lines = _summary_lines(days)
        count = len(days)
        first = days[0][0]
        try:
            create_notification(
                db,
                user_id=employee.user_id,
                type_="attendance_changed" if changed else "attendance_recorded",
                title=f"Attendance updated for {count} day{'s' if count != 1 else ''}",
                message=f"{by} updated your attendance. " + "; ".join(lines) + ".",
                entity_type="attendance_record",
                entity_id=first.id if count == 1 else None,
                target_url=f"/attendance?att_month={first.attendance_date:%Y-%m}",
            )
            db.commit()
        except Exception:
            db.rollback()


def _day_line(record: AttendanceRecord, previous: AttendanceStatus | None) -> str:
    label = service._STATUS_LABELS[record.status]
    if previous is not None:
        label = f"{service._STATUS_LABELS[previous]} -> {label}"
    return f"{service._long_date(record.attendance_date)}: {label}"


def _summary_lines(
    days: list[tuple[AttendanceRecord, AttendanceStatus | None]],
) -> list[str]:
    """The notification body, one span per new status rather than one line per day.

        13 October 2026 to 19 October 2026: Leave (6 days); 14 October 2026: Absent -> Leave

    The day count stays in the span because the days need not be consecutive (a
    skipped Sunday sits inside it), so "13 to 19" alone would overstate it. Days
    that changed FROM another status are still named one by one, since that is
    the part the employee did not already have. A single day keeps the plain
    per-day line. `days` is sorted by date.
    """
    by_status: dict[AttendanceStatus, list] = defaultdict(list)
    for record, previous in days:
        by_status[record.status].append((record, previous))

    lines: list[str] = []
    for status, group in by_status.items():
        if len(group) == 1:
            lines.append(_day_line(*group[0]))
            continue
        first, last = group[0][0].attendance_date, group[-1][0].attendance_date
        lines.append(
            f"{service._long_date(first)} to {service._long_date(last)}: "
            f"{service._STATUS_LABELS[status]} ({len(group)} days)"
        )
        changes = [(r, prev) for r, prev in group if prev is not None]
        lines.extend(_day_line(r, prev) for r, prev in changes[:_NOTIFY_MAX_DAYS])
        if len(changes) > _NOTIFY_MAX_DAYS:
            lines.append(f"and {len(changes) - _NOTIFY_MAX_DAYS} more changed")
    return lines


def _response(
    items: list[_Item],
    employees: dict[uuid.UUID, Employee],
    data: AttendanceBulkApply,
    bulk_action_id: uuid.UUID | None,
) -> dict:
    summary = {k: 0 for k in ("created", "updated", "unchanged", "protected", "rejected")}
    results = []
    for item in items:
        summary[item.outcome] += 1
        employee = employees.get(item.employee_id)
        results.append(
            {
                "employee_id": item.employee_id,
                "employee_code": employee.employee_code if employee else None,
                "employee_name": employee.full_name if employee else None,
                "attendance_date": item.attendance_date,
                "outcome": item.outcome,
                "reason_code": item.reason_code,
                "message": item.message,
                "record_id": item.record.id if item.record is not None else None,
                "previous_status": item.previous_status,
                "status": item.status,
                "warnings": item.warnings,
            }
        )
    return {
        "dry_run": data.dry_run,
        "bulk_action_id": bulk_action_id,
        "status": data.status,
        "summary": summary,
        "results": results,
    }
