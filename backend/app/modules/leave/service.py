"""Leave Request service: RBAC-scoped reads + employee writes + manager review.

RBAC:
  admin    full access — list all, approve/reject any
  manager  list own + team (direct reports); approve/reject team requests
  employee list own requests; create/update/cancel own pending

Workflow:
  pending → approved   (manager/admin)
  pending → rejected   (manager/admin, comment optional)
  pending → cancelled  (employee, own pending only)
  rejected → (re-open by editing → back to pending? No: employee must create new)
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave.schemas import LeaveRequestCreate, LeaveRequestUpdate, LeaveReviewBody
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _team_ids(manager_employee_id: uuid.UUID):
    return select(Employee.id).where(
        Employee.manager_id == manager_employee_id, Employee.deleted_at.is_(None)
    )


# ---------- scope helpers --------------------------------------------------

def _apply_scope(db: Session, actor: User, stmt):
    if actor.role == UserRole.admin:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    if actor.role == UserRole.manager:
        return (
            stmt.where(
                (LeaveRequest.employee_id == me.id)
                | (LeaveRequest.employee_id.in_(_team_ids(me.id)))
            ),
            True,
        )
    # employee
    return stmt.where(LeaveRequest.employee_id == me.id), True


def _assert_can_read(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role == UserRole.admin:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if req.employee_id == me.id:
        return
    if actor.role == UserRole.manager:
        emp = db.get(Employee, req.employee_id)
        if emp is not None and emp.manager_id == me.id:
            return
        raise AppError("forbidden", "You can only view your team's leave requests.", 403)
    raise AppError("forbidden", "You can only view your own leave requests.", 403)


def _assert_can_review(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role == UserRole.admin:
        return
    if actor.role != UserRole.manager:
        raise AppError("forbidden", "Only managers and admins can review leave requests.", 403)
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    emp = db.get(Employee, req.employee_id)
    if emp is not None and emp.manager_id == me.id:
        return
    raise AppError("forbidden", "You can only review your team's leave requests.", 403)


def _fetch(db: Session, req_id: uuid.UUID) -> LeaveRequest:
    req = db.get(LeaveRequest, req_id)
    if req is None:
        raise AppError("not_found", "Leave request not found.", 404)
    return req


def _author_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error",
            "You need an employee profile to submit a leave request.",
            422,
        )
    return me


# ---------- reads ----------------------------------------------------------

def list_leave_requests(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    status: LeaveStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[LeaveRequest], int]:
    stmt = select(LeaveRequest)
    stmt, allowed = _apply_scope(db, actor, stmt)
    if not allowed:
        return [], 0

    if employee_id is not None:
        stmt = stmt.where(LeaveRequest.employee_id == employee_id)
    if status is not None:
        stmt = stmt.where(LeaveRequest.status == status)
    if date_from is not None:
        stmt = stmt.where(LeaveRequest.start_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(LeaveRequest.end_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(LeaveRequest.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_leave_request(db: Session, actor: User, req_id: uuid.UUID) -> LeaveRequest:
    req = _fetch(db, req_id)
    _assert_can_read(db, actor, req)
    return req


# ---------- employee writes -----------------------------------------------

def create_leave_request(
    db: Session, actor: User, data: LeaveRequestCreate
) -> LeaveRequest:
    me = _author_employee(db, actor)
    if data.end_date < data.start_date:
        raise AppError("validation_error", "End date cannot be before start date.", 422)

    req = LeaveRequest(
        employee_id=me.id,
        leave_type=data.leave_type,
        start_date=data.start_date,
        end_date=data.end_date,
        reason=data.reason,
        status=LeaveStatus.pending,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def update_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveRequestUpdate
) -> LeaveRequest:
    req = _fetch(db, req_id)
    me = _author_employee(db, actor)
    if req.employee_id != me.id:
        raise AppError("forbidden", "You can only edit your own leave requests.", 403)
    if req.status != LeaveStatus.pending:
        raise AppError("forbidden", "Only pending requests can be edited.", 403)

    fields = data.model_dump(exclude_unset=True)
    new_start = fields.get("start_date", req.start_date)
    new_end = fields.get("end_date", req.end_date)
    if new_end < new_start:
        raise AppError("validation_error", "End date cannot be before start date.", 422)

    for key, value in fields.items():
        setattr(req, key, value)
    req.updated_by = actor.id
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def cancel_leave_request(db: Session, actor: User, req_id: uuid.UUID) -> LeaveRequest:
    req = _fetch(db, req_id)
    me = _author_employee(db, actor)
    if req.employee_id != me.id:
        raise AppError("forbidden", "You can only cancel your own leave requests.", 403)
    if req.status != LeaveStatus.pending:
        raise AppError("forbidden", "Only pending requests can be cancelled.", 403)

    req.status = LeaveStatus.cancelled
    req.updated_by = actor.id
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


# ---------- manager / admin review ----------------------------------------

def approve_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveReviewBody
) -> LeaveRequest:
    req = _fetch(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.pending:
        raise AppError("validation_error", "Only pending requests can be approved.", 422)

    reviewer = _current_employee(db, actor)
    req.status = LeaveStatus.approved
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.updated_by = actor.id
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


def reject_leave_request(
    db: Session, actor: User, req_id: uuid.UUID, data: LeaveReviewBody
) -> LeaveRequest:
    req = _fetch(db, req_id)
    _assert_can_review(db, actor, req)
    if req.status != LeaveStatus.pending:
        raise AppError("validation_error", "Only pending requests can be rejected.", 422)

    reviewer = _current_employee(db, actor)
    req.status = LeaveStatus.rejected
    req.manager_id = reviewer.id if reviewer else None
    req.manager_comment = data.comment
    req.updated_by = actor.id
    db.add(req)
    db.commit()
    db.refresh(req)
    return req
