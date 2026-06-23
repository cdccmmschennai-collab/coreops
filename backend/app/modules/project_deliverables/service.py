"""Project deliverables service.

RBAC:
  project_manager  full CRUD on any project
  team_lead        full CRUD on projects they lead
  contributor/qc   read-only on their assigned projects
  non-member       no access
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.project_deliverables.models import (
    DeliverableChange,
    DeliverableChangeField,
    DeliverableStatus,
    ProjectDeliverable,
)
from app.modules.project_deliverables.schemas import DeliverableCreate, DeliverableUpdate
from app.modules.projects.models import Project, ProjectMember, ProjectMemberRole
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

def _assert_member(db: Session, actor: User, project_id: uuid.UUID) -> None:
    """Raise 403 if the actor has no access to this project at all."""
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "No access to this project.", 403)
    if not db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == me.id,
        )
    ).first():
        raise AppError("forbidden", "You can only view deliverables for projects you're assigned to.", 403)


def _assert_can_manage(db: Session, actor: User, project_id: uuid.UUID) -> None:
    """Raise 403 unless actor is PM or team lead on this project."""
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is not None and db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == me.id,
            ProjectMember.role == ProjectMemberRole.team_lead,
        )
    ).first():
        return
    raise AppError("forbidden", "Only project managers and team leads may modify deliverables.", 403)


def _fetch_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return project


def _fetch_deliverable(
    db: Session, project_id: uuid.UUID, deliverable_id: uuid.UUID
) -> ProjectDeliverable:
    d = db.execute(
        select(ProjectDeliverable).where(
            ProjectDeliverable.id == deliverable_id,
            ProjectDeliverable.project_id == project_id,
        )
    ).scalar_one_or_none()
    if d is None:
        raise AppError("not_found", "Deliverable not found.", 404)
    return d


def _attach_owner_names(db: Session, rows: list[ProjectDeliverable]) -> None:
    """Bulk-fetch employee names and attach as owner_name."""
    emp_ids = {r.owner_employee_id for r in rows if r.owner_employee_id}
    if not emp_ids:
        for r in rows:
            r.owner_name = None  # type: ignore[attr-defined]
        return
    employees = db.execute(
        select(Employee.id, Employee.full_name).where(Employee.id.in_(emp_ids))
    ).all()
    by_id = {e.id: e.full_name for e in employees}
    for r in rows:
        r.owner_name = by_id.get(r.owner_employee_id) if r.owner_employee_id else None  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_all_deliverables(
    db: Session,
    actor: User,
) -> list[ProjectDeliverable]:
    """Return all deliverables visible to the actor, across all their projects."""
    from app.modules.projects.service import _alive

    if actor.role == UserRole.project_manager:
        project_ids_stmt = select(Project.id).where(Project.deleted_at.is_(None))
    else:
        me = _current_employee(db, actor)
        if me is None:
            return []
        project_ids_stmt = (
            select(ProjectMember.project_id)
            .where(ProjectMember.employee_id == me.id)
        )

    project_ids = db.execute(project_ids_stmt).scalars().all()
    if not project_ids:
        return []

    rows = (
        db.execute(
            select(ProjectDeliverable)
            .where(ProjectDeliverable.project_id.in_(project_ids))
            .order_by(
                ProjectDeliverable.target_date.asc().nulls_last(),
                ProjectDeliverable.created_at.asc(),
            )
        )
        .scalars()
        .all()
    )
    _attach_owner_names(db, list(rows))
    _attach_project_names(db, list(rows))
    return list(rows)


def _attach_project_names(db: Session, rows: list[ProjectDeliverable]) -> None:
    proj_ids = {r.project_id for r in rows}
    if not proj_ids:
        return
    projects = db.execute(
        select(Project.id, Project.name, Project.code).where(Project.id.in_(proj_ids))
    ).all()
    by_id = {p.id: (p.name, p.code) for p in projects}
    for r in rows:
        name, code = by_id.get(r.project_id, (None, None))
        r.project_name = name  # type: ignore[attr-defined]
        r.project_code = code  # type: ignore[attr-defined]


def list_deliverables(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
) -> list[ProjectDeliverable]:
    _fetch_project(db, project_id)
    _assert_member(db, actor, project_id)

    rows = (
        db.execute(
            select(ProjectDeliverable)
            .where(ProjectDeliverable.project_id == project_id)
            .order_by(ProjectDeliverable.target_date.asc().nulls_last(), ProjectDeliverable.created_at.asc())
        )
        .scalars()
        .all()
    )
    _attach_owner_names(db, list(rows))
    return list(rows)


def create_deliverable(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    data: DeliverableCreate,
) -> ProjectDeliverable:
    _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project_id)

    d = ProjectDeliverable(
        project_id=project_id,
        **data.model_dump(),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    _attach_owner_names(db, [d])
    return d


def _date_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def update_deliverable(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    data: DeliverableUpdate,
) -> ProjectDeliverable:
    _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project_id)

    d = _fetch_deliverable(db, project_id, deliverable_id)

    payload = data.model_dump(exclude_unset=True)
    raw_reason = payload.pop("reason", None)
    reason = raw_reason.strip() if isinstance(raw_reason, str) else None

    # Detect tracked changes (planned start date, due date, status reversal)
    # against the current values before applying the update.
    tracked: list[tuple[str, str | None, str | None]] = []

    if "planned_start_date" in payload and payload["planned_start_date"] != d.planned_start_date:
        tracked.append((
            DeliverableChangeField.PLANNED_START_DATE,
            _date_str(d.planned_start_date),
            _date_str(payload["planned_start_date"]),
        ))

    if "target_date" in payload and payload["target_date"] != d.target_date:
        tracked.append((
            DeliverableChangeField.DUE_DATE,
            _date_str(d.target_date),
            _date_str(payload["target_date"]),
        ))

    if "status" in payload and payload["status"] != d.status:
        # Only a reversal *out of* completed is a tracked change requiring a reason.
        if d.status == DeliverableStatus.completed and payload["status"] != DeliverableStatus.completed:
            tracked.append((
                DeliverableChangeField.STATUS,
                d.status.value,
                payload["status"].value,
            ))

    if tracked and not reason:
        raise AppError(
            "validation_error",
            "A reason is required when changing the planned start date, due date, "
            "or reverting a completed deliverable.",
            422,
        )

    for field, value in payload.items():
        setattr(d, field, value)

    for field_name, old_value, new_value in tracked:
        db.add(
            DeliverableChange(
                deliverable_id=d.id,
                field=field_name,
                old_value=old_value,
                new_value=new_value,
                changed_by=actor.id,
                reason=reason,
            )
        )
        audit.record_audit(
            db,
            action=AuditAction.DELIVERABLE_FIELD_CHANGE,
            actor=actor,
            entity_type=EntityType.DELIVERABLE,
            entity_id=d.id,
            details={
                "field": field_name,
                "old": old_value,
                "new": new_value,
                "reason": reason,
            },
        )

    db.commit()
    db.refresh(d)
    _attach_owner_names(db, [d])
    return d


def get_deliverable(
    db: Session, actor: User, deliverable_id: uuid.UUID
) -> ProjectDeliverable:
    """Fetch a single deliverable by id (project resolved from the row)."""
    d = db.get(ProjectDeliverable, deliverable_id)
    if d is None:
        raise AppError("not_found", "Deliverable not found.", 404)
    _fetch_project(db, d.project_id)
    _assert_member(db, actor, d.project_id)
    _attach_owner_names(db, [d])
    _attach_project_names(db, [d])
    return d


def list_deliverable_changes(
    db: Session, actor: User, deliverable_id: uuid.UUID
) -> list[DeliverableChange]:
    d = db.get(ProjectDeliverable, deliverable_id)
    if d is None:
        raise AppError("not_found", "Deliverable not found.", 404)
    _fetch_project(db, d.project_id)
    _assert_member(db, actor, d.project_id)

    rows = db.execute(
        select(DeliverableChange)
        .where(DeliverableChange.deliverable_id == deliverable_id)
        .order_by(DeliverableChange.changed_at.desc())
    ).scalars().all()

    user_ids = {r.changed_by for r in rows}
    names: dict[uuid.UUID, str] = {}
    if user_ids:
        user_rows = db.execute(
            select(User).where(User.id.in_(user_ids))
        ).scalars().all()
        names = {u.id: u.email for u in user_rows}
    for r in rows:
        r.changed_by_name = names.get(r.changed_by, "")  # type: ignore[attr-defined]
    return list(rows)


def delete_deliverable(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
) -> None:
    _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project_id)

    d = _fetch_deliverable(db, project_id, deliverable_id)
    db.delete(d)
    db.commit()
