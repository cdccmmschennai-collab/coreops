"""ActivityRequest service.

Employees create a request (one click on the work-report form); the project's
PM approves or rejects it from the Activity Requests page. Nothing here touches
work reports, activities, or benchmarks — it is purely a request + notify flow.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.activity_requests.models import ActivityRequest, ActivityRequestStatus
from app.modules.activity_requests.schemas import ActivityRequestCreate
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import Project, ProjectManager
from app.modules.tasks.models import Task
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_pm(actor: User) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "Only project managers can manage activity requests.", 403
        )


def _fetch_request(db: Session, request_id: uuid.UUID) -> ActivityRequest:
    req = db.get(ActivityRequest, request_id)
    if req is None:
        raise AppError("not_found", "Activity request not found.", 404)
    return req


def _pm_user_ids(
    db: Session, project_id: uuid.UUID, employee: Employee
) -> list[uuid.UUID]:
    """User ids of the project's assigned PMs. Falls back to the employee's
    reporting PM when the project has no explicit PM assignment."""
    ids = set(
        db.execute(
            select(ProjectManager.user_id).where(
                ProjectManager.project_id == project_id
            )
        ).scalars().all()
    )
    if not ids and employee.reporting_pm_id is not None:
        ids.add(employee.reporting_pm_id)
    return [i for i in ids if i is not None]


def _attach_names(db: Session, requests: list[ActivityRequest]) -> None:
    if not requests:
        return

    emp_ids = {r.employee_id for r in requests}
    project_ids = {r.project_id for r in requests}
    am_ids = {r.sub_activity_id for r in requests}
    am_ids |= {r.activity_id for r in requests if r.activity_id}
    task_ids = {r.task_id for r in requests if r.task_id}

    employees = {
        e.id: e
        for e in db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
        .scalars().all()
    }
    projects = {
        p.id: p
        for p in db.execute(select(Project).where(Project.id.in_(project_ids)))
        .scalars().all()
    }
    activities = {
        a.id: a
        for a in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(am_ids)))
        .scalars().all()
    } if am_ids else {}
    tasks = {
        t.id: t
        for t in db.execute(select(Task).where(Task.id.in_(task_ids)))
        .scalars().all()
    } if task_ids else {}

    for r in requests:
        emp = employees.get(r.employee_id)
        proj = projects.get(r.project_id)
        sub = activities.get(r.sub_activity_id)
        act = activities.get(r.activity_id) if r.activity_id else None
        task = tasks.get(r.task_id) if r.task_id else None
        r.employee_name = emp.full_name if emp else ""  # type: ignore[attr-defined]
        r.project_name = proj.name if proj else ""  # type: ignore[attr-defined]
        r.project_code = proj.code if proj else ""  # type: ignore[attr-defined]
        r.activity_name = act.name if act else None  # type: ignore[attr-defined]
        r.sub_activity_name = sub.name if sub else ""  # type: ignore[attr-defined]
        r.task_title = task.title if task else None  # type: ignore[attr-defined]


def _notify(
    db: Session,
    *,
    user_ids: list[uuid.UUID],
    type_: str,
    title: str,
    message: str,
    request_id: uuid.UUID,
    target_url: str | None,
) -> None:
    """Best-effort fan-out; a notification failure must not roll back the
    request change the caller already committed."""
    if not user_ids:
        return
    try:
        from app.modules.notifications.service import create_notification

        for uid in user_ids:
            create_notification(
                db,
                user_id=uid,
                type_=type_,
                title=title,
                message=message,
                entity_type="activity_request",
                entity_id=request_id,
                target_url=target_url,
            )
        db.commit()
    except Exception:
        db.rollback()


# ── public API ────────────────────────────────────────────────────────────────

def create_request(
    db: Session, actor: User, data: ActivityRequestCreate
) -> ActivityRequest:
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can request activities.", 403)

    project = db.get(Project, data.project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)

    req = ActivityRequest(
        employee_id=employee.id,
        project_id=data.project_id,
        activity_id=data.activity_id,
        sub_activity_id=data.sub_activity_id,
        task_id=data.task_id,
        tags_count=data.tags_count,
        docs_count=data.docs_count,
        bom_count=data.bom_count,
        spares_count=data.spares_count,
        status=ActivityRequestStatus.pending.value,
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])
    _notify(
        db,
        user_ids=_pm_user_ids(db, data.project_id, employee),
        type_="activity_request_created",
        title="New activity request",
        message=(
            f"{req.employee_name} requested activity "  # type: ignore[attr-defined]
            f"'{req.sub_activity_name}' on {req.project_code}."  # type: ignore[attr-defined]
        ),
        request_id=req.id,
        target_url="/activity-requests",
    )
    return req


def list_requests(
    db: Session, actor: User, status: ActivityRequestStatus | None = None
) -> list[ActivityRequest]:
    _require_pm(actor)
    stmt = select(ActivityRequest)
    if status is not None:
        stmt = stmt.where(ActivityRequest.status == status.value)
    rows = list(
        db.execute(stmt.order_by(ActivityRequest.requested_at.desc())).scalars().all()
    )
    _attach_names(db, rows)
    return rows


def pending_count(db: Session, actor: User) -> int:
    _require_pm(actor)
    from sqlalchemy import func

    return db.execute(
        select(func.count())
        .select_from(ActivityRequest)
        .where(ActivityRequest.status == ActivityRequestStatus.pending.value)
    ).scalar_one()


def _decide(
    db: Session,
    actor: User,
    request_id: uuid.UUID,
    new_status: ActivityRequestStatus,
) -> ActivityRequest:
    _require_pm(actor)
    req = _fetch_request(db, request_id)
    if req.status != ActivityRequestStatus.pending.value:
        raise AppError(
            "validation_error", "This request has already been decided.", 422
        )

    req.status = new_status.value
    req.approved_by = actor.id
    req.approved_at = datetime.now(timezone.utc)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])

    employee = db.get(Employee, req.employee_id)
    employee_user_ids = (
        [employee.user_id] if employee and employee.user_id else []
    )
    decided = "approved" if new_status == ActivityRequestStatus.approved else "rejected"
    _notify(
        db,
        user_ids=employee_user_ids,
        type_=f"activity_request_{decided}",
        title=f"Activity request {decided}",
        message=(
            f"Your request for activity '{req.sub_activity_name}' "  # type: ignore[attr-defined]
            f"on {req.project_code} was {decided}."  # type: ignore[attr-defined]
        ),
        request_id=req.id,
        target_url=None,
    )
    return req


def approve_request(
    db: Session, actor: User, request_id: uuid.UUID
) -> ActivityRequest:
    return _decide(db, actor, request_id, ActivityRequestStatus.approved)


def reject_request(
    db: Session, actor: User, request_id: uuid.UUID
) -> ActivityRequest:
    return _decide(db, actor, request_id, ActivityRequestStatus.rejected)
