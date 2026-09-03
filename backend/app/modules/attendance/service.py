"""Attendance service: RBAC-scoped reads + admin writes + minute calculations.

RBAC (this module):
  admin    full access
  manager  read team attendance (employees who report to them)
  employee read own attendance
  viewer   read all
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.attendance.schemas import AttendanceCreate, AttendanceUpdate
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.audit.service import record_audit
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave_balances import ledger
from app.modules.users.models import User, UserRole
from app.modules.work_reports.auto_reports import reconcile_auto_leave_reports
from app.shared.errors import AppError

STANDARD_WORKDAY_MINUTES = 480  # 8 hours; anything beyond counts as overtime


def _reconcile_auto_leave_reports(db: Session, touched: list[AttendanceRecord]) -> None:
    """PHASE 3F: unlock the automatic leave report for any day just ruled NOT
    leave.

    A PM changing a day from Leave to Present does not touch `leave_requests` -
    the two systems stay separate, as they always have - but it does settle what
    the day meant, and an automatic leave report sitting on it is locked against
    the very reporting the employee now owes. So the row is withdrawn (or, if
    somebody has typed on it, reclassified and reopened); see
    `work_reports/auto_reports.py`, "LEAVE RECONCILIATION - PHASE 3F".

    Offered for every written row whose resulting status is not `leave`, which is
    exactly the condition under which the absence can have ended. That is a wider
    net than "was leave, is now present" on purpose: a day whose leave attendance
    row was deleted and then re-entered as present has no previous status to
    compare against, and would slip through the narrower test.

    One batched call, no commit: the attendance write and the reports it unlocks
    belong to the caller's single transaction. A day still on leave, a day with
    no automatic report, and an employee-authored report are all no-ops.
    """
    pairs = [
        (record.employee_id, record.attendance_date)
        for record in touched
        if record.status != AttendanceStatus.leave
    ]
    if pairs:
        reconcile_auto_leave_reports(db, pairs, commit=False)


def _validated_leave_fraction(
    fraction: Decimal | float | None, status: AttendanceStatus
) -> Decimal | None:
    """The leave fraction to store for a day of this status.

    The SHAPE of the value is already checked by the schema (0, 0.5 or 1). What
    is checked here is whether it makes sense on this day at all: only `leave`
    and `half_day` can be funded absence, so a fraction on a `present` or
    `holiday` row is a caller mistake and is refused rather than stored where
    `leave_days_for` would ignore it. A row nobody can explain is worse than an
    error message.
    """
    if fraction is None:
        return None
    if status not in ledger.LEAVE_BEARING_STATUSES:
        raise AppError(
            "validation_error",
            "Only a Leave or Half day can be charged to the leave balance.",
            422,
        )
    return Decimal(str(fraction))


def _clean_note(value: str | None) -> str | None:
    """Whitespace-only is no note. Keeps "  " out of the column so the UI can
    treat NULL as the single "no reason given" case."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _audit_record(
    db: Session,
    *,
    actor: User,
    action: str,
    record: AttendanceRecord,
    note: str | None,
    previous_status: AttendanceStatus | None,
) -> None:
    """Record who decided what a day means, and why. FLUSHES, never commits.

    Attendance had no audit trail at all before this. It needs one precisely
    BECAUSE biometric evidence is immutable: punches cannot change, so the only
    way a day's official meaning changes is a human deciding it did, and that
    decision should never be anonymous.

    The PM's `note` is carried here rather than on the row. `attendance_records`
    has no note column, and adding one is a migration - the reasoning behind a
    change is also genuinely audit-shaped: it explains an event, not the current
    state of the day.
    """
    details: dict = {
        "employee_id": str(record.employee_id),
        "attendance_date": record.attendance_date.isoformat(),
        "status": record.status.value,
        "check_in_at": record.check_in_at.isoformat() if record.check_in_at else None,
        "check_out_at": record.check_out_at.isoformat() if record.check_out_at else None,
        "total_minutes": record.total_minutes,
    }
    # Audited because it SPENDS LEAVE. "Who charged me half a day" has to be
    # answerable from the same trail as "who marked me half-day", and the two are
    # now separate decisions about the same row.
    if record.leave_day_fraction is not None:
        details["leave_day_fraction"] = float(record.leave_day_fraction)
    if previous_status is not None and previous_status != record.status:
        details["previous_status"] = previous_status.value
    if note and note.strip():
        details["note"] = note.strip()

    record_audit(
        db,
        action=action,
        actor=actor,
        entity_type=EntityType.ATTENDANCE_RECORD,
        entity_id=record.id,
        details=details,
    )
def _compute_minutes(
    check_in: datetime | None, check_out: datetime | None
) -> tuple[int, int]:
    if check_in is None or check_out is None:
        return 0, 0
    minutes = int((check_out - check_in).total_seconds() // 60)
    if minutes < 0:
        minutes = 0
    return minutes, max(0, minutes - STANDARD_WORKDAY_MINUTES)


def _team_ids(db: Session, manager_employee_id: uuid.UUID):
    return select(Employee.id).where(
        Employee.manager_id == manager_employee_id, Employee.deleted_at.is_(None)
    )


# ---------- reads ----------------------------------------------------------
def _apply_scope(db: Session, actor: User, stmt):
    """Return (stmt, allowed). allowed=False short-circuits to an empty page."""
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    return stmt.where(AttendanceRecord.employee_id == me.id), True


def list_attendance(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    status: AttendanceStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[AttendanceRecord], int]:
    stmt = select(AttendanceRecord)
    stmt, allowed = _apply_scope(db, actor, stmt)
    if not allowed:
        return [], 0

    if employee_id is not None:
        stmt = stmt.where(AttendanceRecord.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(AttendanceRecord.status == status)
    if date_from is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AttendanceRecord.attendance_date.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def _assert_can_read(db: Session, actor: User, record: AttendanceRecord) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if record.employee_id == me.id:
        return
    raise AppError("forbidden", "You can only view your own attendance.", 403)


def _fetch(db: Session, record_id: uuid.UUID) -> AttendanceRecord:
    record = db.get(AttendanceRecord, record_id)
    if record is None:
        raise AppError("not_found", "Attendance record not found.", 404)
    return record


def get_attendance(db: Session, actor: User, record_id: uuid.UUID) -> AttendanceRecord:
    record = _fetch(db, record_id)
    _assert_can_read(db, actor, record)
    return record


def _assert_can_read_employee(db: Session, actor: User, employee: Employee) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if employee.id == me.id:
        return
    raise AppError("forbidden", "Not permitted.", 403)


def list_employee_attendance(
    db: Session,
    actor: User,
    employee_id: uuid.UUID,
    *,
    status: AttendanceStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[AttendanceRecord], int]:
    employee = db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise AppError("not_found", "Employee not found.", 404)
    _assert_can_read_employee(db, actor, employee)

    stmt = select(AttendanceRecord).where(AttendanceRecord.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(AttendanceRecord.status == status)
    if date_from is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(AttendanceRecord.attendance_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AttendanceRecord.attendance_date.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


# ---------- writes (admin) -------------------------------------------------
def create_attendance(db: Session, actor: User, data: AttendanceCreate) -> AttendanceRecord:
    employee = db.get(Employee, data.employee_id)
    if employee is None or employee.deleted_at is not None:
        raise AppError("validation_error", "Employee not found.", 422)

    if (
        data.check_in_at is not None
        and data.check_out_at is not None
        and data.check_out_at < data.check_in_at
    ):
        raise AppError("validation_error", "Check-out cannot be before check-in.", 422)

    if db.execute(
        select(AttendanceRecord).where(
            AttendanceRecord.employee_id == data.employee_id,
            AttendanceRecord.attendance_date == data.attendance_date,
        )
    ).scalar_one_or_none():
        raise AppError(
            "conflict", "Attendance for this employee and date already exists.", 409
        )

    total, overtime = _compute_minutes(data.check_in_at, data.check_out_at)
    record = AttendanceRecord(
        employee_id=data.employee_id,
        attendance_date=data.attendance_date,
        status=data.status,
        check_in_at=data.check_in_at,
        check_out_at=data.check_out_at,
        total_minutes=total,
        overtime_minutes=overtime,
        note=_clean_note(data.note),
        leave_day_fraction=_validated_leave_fraction(
            data.leave_day_fraction, data.status
        ),
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(record)
    try:
        db.flush()
        _audit_record(
            db,
            actor=actor,
            action=AuditAction.ATTENDANCE_RECORD_CREATE,
            record=record,
            note=data.note,
            previous_status=None,
        )
        _reconcile_auto_leave_reports(db, [record])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Attendance violates a uniqueness constraint.", 409)
    db.refresh(record)
    return record


def update_attendance(
    db: Session, actor: User, record_id: uuid.UUID, data: AttendanceUpdate
) -> AttendanceRecord:
    record = _fetch(db, record_id)
    fields = data.model_dump(exclude_unset=True)
    previous_status = record.status

    new_in = fields.get("check_in_at", record.check_in_at)
    new_out = fields.get("check_out_at", record.check_out_at)
    if new_in is not None and new_out is not None and new_out < new_in:
        raise AppError("validation_error", "Check-out cannot be before check-in.", 422)

    if "status" in fields and fields["status"] is not None:
        record.status = fields["status"]
    if "check_in_at" in fields:
        record.check_in_at = fields["check_in_at"]
    if "check_out_at" in fields:
        record.check_out_at = fields["check_out_at"]
    # Only overwrite the stored reason when one was actually sent. A PATCH that
    # changes the status must not silently erase the explanation already there.
    if "note" in fields:
        record.note = _clean_note(fields["note"])
    # Same rule for the leave charge, and one more of its own: a day moved OFF a
    # leave-bearing status keeps no charge behind it. Without that, changing a
    # half-day leave to Present would leave 0.5 stored on a `present` row, which
    # `_validated_leave_fraction` would never have accepted in the first place.
    if "leave_day_fraction" in fields:
        record.leave_day_fraction = _validated_leave_fraction(
            fields["leave_day_fraction"], record.status
        )
    elif record.status not in ledger.LEAVE_BEARING_STATUSES:
        record.leave_day_fraction = None

    record.total_minutes, record.overtime_minutes = _compute_minutes(new_in, new_out)
    record.updated_by = actor.id
    db.add(record)
    db.flush()
    _audit_record(
        db,
        actor=actor,
        action=AuditAction.ATTENDANCE_RECORD_UPDATE,
        record=record,
        note=data.note,
        previous_status=previous_status,
    )
    _reconcile_auto_leave_reports(db, [record])
    db.commit()
    db.refresh(record)
    return record


def delete_attendance(db: Session, actor: User, record_id: uuid.UUID) -> None:
    record = _fetch(db, record_id)
    _audit_record(
        db,
        actor=actor,
        action=AuditAction.ATTENDANCE_RECORD_DELETE,
        record=record,
        note=None,
        previous_status=record.status,
    )
    db.delete(record)
    db.commit()


# ---------- bulk / sheet (admin) -------------------------------------------
def _active_employees(db: Session) -> list[Employee]:
    """All non-deleted employees, ordered for a stable sheet (name, code)."""
    return list(
        db.execute(
            select(Employee)
            .where(Employee.deleted_at.is_(None))
            .order_by(Employee.first_name, Employee.last_name, Employee.employee_code)
        )
        .scalars()
        .all()
    )


def get_attendance_sheet(db: Session, actor: User, attendance_date: date):
    """Return one row per active employee, merged with saved records for the
    date. Employees without a record default to ``present``. Returns
    (rows, exists) where exists is True when any record exists for the date."""
    employees = _active_employees(db)
    records = {
        r.employee_id: r
        for r in db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.attendance_date == attendance_date
            )
        )
        .scalars()
        .all()
    }
    rows = []
    for emp in employees:
        rec = records.get(emp.id)
        rows.append(
            {
                "employee_id": emp.id,
                "employee_code": emp.employee_code,
                "employee_name": emp.full_name,
                "status": rec.status if rec else AttendanceStatus.present,
                "record_id": rec.id if rec else None,
                "check_in_at": rec.check_in_at if rec else None,
                "check_out_at": rec.check_out_at if rec else None,
                "total_minutes": rec.total_minutes if rec else 0,
                "overtime_minutes": rec.overtime_minutes if rec else 0,
            }
        )
    return rows, bool(records)


def bulk_save_attendance(
    db: Session, actor: User, attendance_date: date, records: list
) -> None:
    """Upsert every record in a single transaction (no partial saves).

    Existing (employee, date) rows are updated; the rest are inserted. An
    unknown/deleted employee or invalid check-in/out aborts the whole batch.
    """
    if not records:
        return

    employee_ids = [r.employee_id for r in records]
    valid_ids = {
        e for e in db.execute(
            select(Employee.id).where(
                Employee.id.in_(employee_ids), Employee.deleted_at.is_(None)
            )
        ).scalars().all()
    }
    unknown = set(employee_ids) - valid_ids
    if unknown:
        raise AppError("validation_error", "One or more employees were not found.", 422)

    existing = {
        r.employee_id: r
        for r in db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.attendance_date == attendance_date,
                AttendanceRecord.employee_id.in_(employee_ids),
            )
        )
        .scalars()
        .all()
    }

    # (record, was_created, previous_status) for the audit pass below.
    touched: list[tuple[AttendanceRecord, bool, AttendanceStatus | None]] = []

    for item in records:
        if (
            item.check_in_at is not None
            and item.check_out_at is not None
            and item.check_out_at < item.check_in_at
        ):
            raise AppError(
                "validation_error", "Check-out cannot be before check-in.", 422
            )
        total, overtime = _compute_minutes(item.check_in_at, item.check_out_at)
        record = existing.get(item.employee_id)
        created = record is None
        previous_status = None if created else record.status
        if record is None:
            record = AttendanceRecord(
                employee_id=item.employee_id,
                attendance_date=attendance_date,
                created_by=actor.id,
            )
            db.add(record)
        record.status = item.status
        record.check_in_at = item.check_in_at
        record.check_out_at = item.check_out_at
        record.total_minutes = total
        record.overtime_minutes = overtime
        record.updated_by = actor.id
        touched.append((record, created, previous_status))

    try:
        # Audited per employee-day, not per batch: one row here is one decision
        # about one person, and "who marked me half-day" has to be answerable
        # afterwards. Flushed first so an inserted record has its id.
        db.flush()
        for record, created, previous_status in touched:
            _audit_record(
                db,
                actor=actor,
                action=(
                    AuditAction.ATTENDANCE_RECORD_CREATE
                    if created
                    else AuditAction.ATTENDANCE_RECORD_UPDATE
                ),
                record=record,
                note=None,
                previous_status=previous_status,
            )
        _reconcile_auto_leave_reports(db, [record for record, _, _ in touched])
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Attendance violates a uniqueness constraint.", 409)
