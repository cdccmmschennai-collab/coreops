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
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.leave.models import LeaveRequest, LeaveStatus
from app.modules.leave.schemas import (
    DeliverableConflictOut,
    LeaveDeliverableImpactOut,
    LeaveRequestCreate,
    LeaveRequestUpdate,
    LeaveReviewBody,
)
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

# Number of calendar days before/after a deliverable's planned date that a
# leave day must fall within to count as a Deliverable Impact.
DELIVERABLE_IMPACT_WINDOW = timedelta(days=2)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None, target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="leave_request", entity_id=entity_id,
                            target_url=target_url)
        db.commit()
    except Exception:
        db.rollback()


def _notify_manager(db: Session, employee: Employee, type_: str, title: str,
                    message: str, entity_id: uuid.UUID | None = None,
                    target_url: str | None = None) -> None:
    if employee.manager_id is None:
        return
    mgr = db.get(Employee, employee.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(db, mgr.user_id, type_, title, message, entity_id, target_url)


def _notify_employee(db: Session, employee_id: uuid.UUID, type_: str, title: str,
                     message: str, entity_id: uuid.UUID | None = None,
                     target_url: str | None = None) -> None:
    emp = db.get(Employee, employee_id)
    if emp is None or emp.user_id is None:
        return
    _push(db, emp.user_id, type_, title, message, entity_id, target_url)


def _team_ids(manager_employee_id: uuid.UUID):
    return select(Employee.id).where(
        Employee.manager_id == manager_employee_id, Employee.deleted_at.is_(None)
    )


# ---------- scope helpers --------------------------------------------------

def _apply_scope(db: Session, actor: User, stmt):
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    return stmt.where(LeaveRequest.employee_id == me.id), True


def _assert_can_read(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if req.employee_id == me.id:
        return
    raise AppError("forbidden", "You can only view your own leave requests.", 403)


def _assert_can_review(db: Session, actor: User, req: LeaveRequest) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Only project managers can review leave requests.", 403)


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
    _notify_manager(
        db, me, "leave_submitted",
        f"{me.full_name} submitted a leave request",
        f"{me.full_name} requested {data.leave_type.value} leave from {data.start_date} to {data.end_date}.",
        req.id,
        f"/attendance?tab=leave&id={req.id}",
    )
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
    _notify_manager(
        db, me, "leave_cancelled",
        f"{me.full_name} cancelled a leave request",
        f"{me.full_name} cancelled their leave request ({req.start_date} to {req.end_date}).",
        req.id,
        f"/attendance?tab=leave&id={req.id}",
    )
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
    _notify_employee(
        db, req.employee_id, "leave_approved",
        "Your leave request was approved",
        f"Your leave request ({req.start_date} to {req.end_date}) has been approved.",
        req.id,
        f"/attendance?tab=leave&id={req.id}",
    )
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
    _notify_employee(
        db, req.employee_id, "leave_rejected",
        "Your leave request was rejected",
        f"Your leave request ({req.start_date} to {req.end_date}) was not approved."
        + (f" Note: {data.comment}" if data.comment else ""),
        req.id,
        f"/attendance?tab=leave&id={req.id}",
    )
    return req


# ---------- deliverable impact (decision support) --------------------------

def deliverable_impacts(
    db: Session, actor: User, leave_request_ids: list[uuid.UUID]
) -> list[LeaveDeliverableImpactOut]:
    """For the given leave requests, find Planned deliverables whose target
    date falls within ±2 days of the requested leave, on projects the
    requesting employee is assigned to.

    Informational only — never blocks approval. Computed in a handful of bulk
    queries for the whole displayed page (no per-row querying).
    """
    from app.modules.project_deliverables.models import (
        DeliverableStatus,
        ProjectDeliverable,
    )
    from app.modules.projects.models import Project, ProjectMember

    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "Only project managers can review deliverable impact.", 403
        )
    if not leave_request_ids:
        return []

    reqs = (
        db.execute(
            select(LeaveRequest).where(LeaveRequest.id.in_(leave_request_ids))
        )
        .scalars()
        .all()
    )
    if not reqs:
        return []

    employee_ids = {r.employee_id for r in reqs}

    # employee → set of project ids they belong to
    member_rows = db.execute(
        select(ProjectMember.employee_id, ProjectMember.project_id).where(
            ProjectMember.employee_id.in_(employee_ids)
        )
    ).all()
    projects_by_emp: dict[uuid.UUID, set[uuid.UUID]] = {}
    project_ids: set[uuid.UUID] = set()
    for emp_id, proj_id in member_rows:
        projects_by_emp.setdefault(emp_id, set()).add(proj_id)
        project_ids.add(proj_id)
    if not project_ids:
        return []

    # Bound the deliverable scan to the widest possible impact window across
    # all displayed requests, so we never scan the whole deliverables table.
    win_lo = min(r.start_date for r in reqs) - DELIVERABLE_IMPACT_WINDOW
    win_hi = max(r.end_date for r in reqs) + DELIVERABLE_IMPACT_WINDOW

    deliv_rows = db.execute(
        select(
            ProjectDeliverable.id.label("deliverable_id"),
            ProjectDeliverable.project_id.label("project_id"),
            ProjectDeliverable.name.label("deliverable_name"),
            ProjectDeliverable.target_date.label("target_date"),
            Project.name.label("project_name"),
            Project.code.label("project_code"),
        )
        .join(Project, Project.id == ProjectDeliverable.project_id)
        .where(
            ProjectDeliverable.project_id.in_(project_ids),
            ProjectDeliverable.status == DeliverableStatus.planned,
            ProjectDeliverable.target_date.is_not(None),
            ProjectDeliverable.target_date >= win_lo,
            ProjectDeliverable.target_date <= win_hi,
            Project.deleted_at.is_(None),
        )
    ).all()
    delivs_by_project: dict[uuid.UUID, list] = {}
    for d in deliv_rows:
        delivs_by_project.setdefault(d.project_id, []).append(d)

    emp_names = {
        row.id: f"{row.first_name} {row.last_name}".strip()
        for row in db.execute(
            select(Employee.id, Employee.first_name, Employee.last_name).where(
                Employee.id.in_(employee_ids)
            )
        ).all()
    }

    items: list[LeaveDeliverableImpactOut] = []
    for r in reqs:
        # Leave [start, end] conflicts with deliverable date D when the leave
        # overlaps [D-2, D+2], i.e. D in [start-2, end+2].
        lo = r.start_date - DELIVERABLE_IMPACT_WINDOW
        hi = r.end_date + DELIVERABLE_IMPACT_WINDOW
        seen: set[uuid.UUID] = set()
        conflicts: list[DeliverableConflictOut] = []
        for proj_id in projects_by_emp.get(r.employee_id, ()):
            for d in delivs_by_project.get(proj_id, ()):
                if d.deliverable_id in seen or not (lo <= d.target_date <= hi):
                    continue
                seen.add(d.deliverable_id)
                conflicts.append(
                    DeliverableConflictOut(
                        deliverable_id=d.deliverable_id,
                        deliverable_name=d.deliverable_name,
                        project_id=d.project_id,
                        project_name=d.project_name,
                        project_code=d.project_code,
                        status=DeliverableStatus.planned.value,
                        target_date=d.target_date,
                        employee_id=r.employee_id,
                        employee_name=emp_names.get(r.employee_id),
                    )
                )
        if conflicts:
            conflicts.sort(key=lambda c: c.target_date or date.max)
            items.append(
                LeaveDeliverableImpactOut(leave_request_id=r.id, conflicts=conflicts)
            )
    return items
