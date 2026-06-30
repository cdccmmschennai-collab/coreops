"""Attendance service: RBAC-scoped reads + admin writes + minute calculations.

RBAC (this module):
  admin    full access
  manager  read team attendance (employees who report to them)
  employee read own attendance
  viewer   read all
"""
import uuid
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.attendance.schemas import AttendanceCreate, AttendanceUpdate
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

STANDARD_WORKDAY_MINUTES = 480  # 8 hours; anything beyond counts as overtime
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
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(record)
    try:
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

    record.total_minutes, record.overtime_minutes = _compute_minutes(new_in, new_out)
    record.updated_by = actor.id
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def delete_attendance(db: Session, actor: User, record_id: uuid.UUID) -> None:
    record = _fetch(db, record_id)
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

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Attendance violates a uniqueness constraint.", 409)
