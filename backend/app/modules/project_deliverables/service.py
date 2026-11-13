"""Project deliverables service.

RBAC (ADR-003 Amendment 2) - resolved through the central `app.core.authz`
helpers, never by project-member role:
  project_manager   view + manage on every live project
  project Head      view + manage on the projects they are assigned Head of
  project member    read-only on the projects they belong to (team_lead,
                    contributor, qc alike - a team-lead role grants nothing more)
  anyone else       no access
"Manage" = create, edit (deadline / status / details) and delete.

Deliverables of soft-deleted projects are invisible to everyone.
"""
import uuid
from datetime import date

from sqlalchemy import select, union
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.project_deliverables.deadline import business_today
from app.modules.project_deliverables.models import (
    DeliverableChange,
    DeliverableChangeField,
    DeliverableStatus,
    ProjectDeliverable,
)
from app.modules.project_deliverables.schemas import DeliverableCreate, DeliverableUpdate
from app.modules.projects.models import Project, ProjectMember
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


# ---------------------------------------------------------------------------
# RBAC helpers
# ---------------------------------------------------------------------------

def _can_manage(db: Session, actor: User, project: Project) -> bool:
    """PM on any project, or the employee assigned as THIS project's Head."""
    if actor.role == UserRole.project_manager:
        return True
    return authz.is_project_head(db, actor, project)


def _assert_member(db: Session, actor: User, project: Project) -> None:
    """Raise 403 unless the actor may view this project (PM, Head or member)."""
    if not authz.can_view_project(db, actor, project):
        raise AppError("forbidden", "You can only view deliverables for projects you're assigned to.", 403)


def _assert_can_manage(db: Session, actor: User, project: Project) -> None:
    """Raise 403 unless the actor is a PM or this project's assigned Head."""
    if not _can_manage(db, actor, project):
        raise AppError(
            "forbidden",
            "Only project managers and the project's Head may modify deliverables.",
            403,
        )


def _attach_can_manage(rows: list[ProjectDeliverable], manageable: set[uuid.UUID] | None) -> None:
    """Stamp the per-row `can_manage` flag. `manageable=None` means every row
    (PM); otherwise only rows whose project id is in the set."""
    for r in rows:
        r.can_manage = manageable is None or r.project_id in manageable  # type: ignore[attr-defined]


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


OWNER_ROLE_HEAD = "project_head"
OWNER_ROLE_EMPLOYEE = "employee"


def _attach_owner_names(db: Session, rows: list[ProjectDeliverable]) -> None:
    """Bulk-fetch the Assignee (owner_employee_id) name and role.

    owner_role is "project_head" when the assignee is the project's current
    Head, otherwise "employee"; both stay None for an unassigned row.
    (`Employee.full_name` is a Python property, so whole rows are loaded.)
    """
    emp_ids = {r.owner_employee_id for r in rows if r.owner_employee_id}
    if not emp_ids:
        for r in rows:
            r.owner_name = None  # type: ignore[attr-defined]
            r.owner_role = None  # type: ignore[attr-defined]
        return
    employees = db.execute(select(Employee).where(Employee.id.in_(emp_ids))).scalars().all()
    names = {e.id: e.full_name for e in employees}
    heads = dict(
        db.execute(
            select(Project.id, Project.head_employee_id).where(
                Project.id.in_({r.project_id for r in rows})
            )
        ).all()
    )
    for r in rows:
        if not r.owner_employee_id:
            r.owner_name = None  # type: ignore[attr-defined]
            r.owner_role = None  # type: ignore[attr-defined]
            continue
        r.owner_name = names.get(r.owner_employee_id)  # type: ignore[attr-defined]
        r.owner_role = (  # type: ignore[attr-defined]
            OWNER_ROLE_HEAD
            if heads.get(r.project_id) == r.owner_employee_id
            else OWNER_ROLE_EMPLOYEE
        )


# ---------------------------------------------------------------------------
# Assignee (owner_employee_id) - who may be assigned
# ---------------------------------------------------------------------------

def _assignable_employees(db: Session, project: Project) -> list[tuple[Employee, str]]:
    """The project's Head plus its project members - the only valid Assignees.

    Soft-deleted and exited employees are excluded. The Head comes first; the
    rest are sorted by name. A Head who is also a member appears once, as Head.
    """
    member_ids = set(
        db.execute(
            select(ProjectMember.employee_id).where(ProjectMember.project_id == project.id)
        ).scalars().all()
    )
    ids = member_ids | ({project.head_employee_id} if project.head_employee_id else set())
    if not ids:
        return []
    employees = db.execute(
        select(Employee).where(
            Employee.id.in_(ids),
            Employee.deleted_at.is_(None),
            Employee.status != EmployeeStatus.exited,
        )
    ).scalars().all()
    head = [(e, OWNER_ROLE_HEAD) for e in employees if e.id == project.head_employee_id]
    rest = sorted(
        ((e, OWNER_ROLE_EMPLOYEE) for e in employees if e.id != project.head_employee_id),
        key=lambda pair: pair[0].full_name.lower(),
    )
    return head + rest


def list_assignees(db: Session, actor: User, project_id: uuid.UUID) -> list[dict]:
    """Assignee options for the create/edit form - managers only."""
    project = _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project)
    return [
        {"employee_id": e.id, "name": e.full_name, "role": role}
        for e, role in _assignable_employees(db, project)
    ]


def _validate_owner(db: Session, project: Project, owner_id: uuid.UUID | None) -> None:
    """Reject any Assignee who is not this project's Head or a project member."""
    if owner_id is None:
        return
    if owner_id not in {e.id for e, _ in _assignable_employees(db, project)}:
        raise AppError(
            "invalid_assignee",
            "The Assignee must be this project's Head or one of its members.",
            422,
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def list_all_deliverables(
    db: Session,
    actor: User,
) -> list[ProjectDeliverable]:
    """Return all deliverables visible to the actor, across all their projects.

    PM: every live project. Others: projects they are a member of or Head of.
    Soft-deleted projects are excluded on both branches.
    """
    manageable: set[uuid.UUID] | None
    if actor.role == UserRole.project_manager:
        project_ids_stmt = select(Project.id).where(Project.deleted_at.is_(None))
        manageable = None
    else:
        me = _current_employee(db, actor)
        if me is None:
            return []
        visible = union(
            select(ProjectMember.project_id.label("pid")).where(
                ProjectMember.employee_id == me.id
            ),
            select(Project.id.label("pid")).where(Project.head_employee_id == me.id),
        ).subquery()
        project_ids_stmt = select(Project.id).where(
            Project.id.in_(select(visible.c.pid)),
            Project.deleted_at.is_(None),
        )
        manageable = set(
            db.execute(
                select(Project.id).where(
                    Project.head_employee_id == me.id,
                    Project.deleted_at.is_(None),
                )
            ).scalars().all()
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
    _attach_can_manage(list(rows), manageable)
    return list(rows)


# ---------------------------------------------------------------------------
# Notifications — only the deliverable's Assignee and the project's Head are
# told when a deliverable is planned, assigned, its delivery date moves, or it
# is completed. Other project members are NOT notified.
# ---------------------------------------------------------------------------

def _deliverable_recipient_user_ids(
    db: Session, project: Project, d: ProjectDeliverable
) -> list[uuid.UUID]:
    """Login user ids of the Assignee and the project Head.

    De-duplicated by user id, so an Assignee who is also the Head is notified
    ONCE. People without a login, and soft-deleted employees, are skipped. An
    unassigned deliverable notifies the Head only.
    """
    emp_ids = {e for e in (d.owner_employee_id, project.head_employee_id) if e}
    if not emp_ids:
        return []
    rows = db.execute(
        select(Employee.user_id).where(
            Employee.id.in_(emp_ids),
            Employee.user_id.is_not(None),
            Employee.deleted_at.is_(None),
        )
    ).scalars().all()
    return sorted({uid for uid in rows if uid is not None}, key=str)


def _notify_members(
    db: Session,
    project: Project,
    d: ProjectDeliverable,
    *,
    type_: str,
    title: str,
    message: str,
) -> None:
    """Send a deliverable event to its Assignee + the project Head. Best-effort:
    a notification failure must not roll back the deliverable change the
    caller already committed."""
    try:
        from app.modules.notifications.service import create_notification

        deliverable_id = d.id
        target_url = f"/projects/deliverables/{deliverable_id}"
        for uid in _deliverable_recipient_user_ids(db, project, d):
            create_notification(
                db,
                user_id=uid,
                type_=type_,
                title=title,
                message=message,
                entity_type="deliverable",
                entity_id=deliverable_id,
                target_url=target_url,
            )
        db.commit()
    except Exception:
        db.rollback()


def _fmt(value: date | None) -> str:
    return value.isoformat() if value else "—"


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
    project = _fetch_project(db, project_id)
    _assert_member(db, actor, project)

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
    _attach_can_manage(list(rows), None if _can_manage(db, actor, project) else set())
    return list(rows)


def create_deliverable(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    data: DeliverableCreate,
) -> ProjectDeliverable:
    project = _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project)
    _validate_owner(db, project, data.owner_employee_id)

    d = ProjectDeliverable(
        project_id=project_id,
        **data.model_dump(),
    )
    db.add(d)
    db.commit()
    db.refresh(d)
    _attach_owner_names(db, [d])
    _attach_can_manage([d], None)

    _notify_members(
        db,
        project,
        d,
        type_="deliverable_planned",
        title="Deliverable Planned",
        message=(
            "A new deliverable has been planned for your project.\n"
            f"Project: {project.name}\n"
            f"Activity: {d.name}\n"
            f"Assignee: {_assignee_text(d)}\n"
            f"Planned Delivery Date: {_fmt(d.target_date)}"
        ),
    )
    return d


def _assignee_text(d: ProjectDeliverable) -> str:
    return getattr(d, "owner_name", None) or "Unassigned"


def _date_str(value: date | None) -> str | None:
    return value.isoformat() if value else None


def update_deliverable(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    deliverable_id: uuid.UUID,
    data: DeliverableUpdate,
) -> ProjectDeliverable:
    project = _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project)

    d = _fetch_deliverable(db, project_id, deliverable_id)

    # Snapshot the fields that drive notifications before the update is applied.
    prev_target_date = d.target_date
    prev_status = d.status
    prev_owner = d.owner_employee_id

    payload = data.model_dump(exclude_unset=True)
    raw_reason = payload.pop("reason", None)
    reason = raw_reason.strip() if isinstance(raw_reason, str) else None

    # Only a CHANGED Assignee is validated, so an unrelated edit never fails
    # because an earlier Assignee has since left the project.
    if "owner_employee_id" in payload and payload["owner_employee_id"] != d.owner_employee_id:
        _validate_owner(db, project, payload["owner_employee_id"])

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
        # Only a reversal *out of* completed is a tracked change.
        if d.status == DeliverableStatus.completed and payload["status"] != DeliverableStatus.completed:
            tracked.append((
                DeliverableChangeField.STATUS,
                d.status.value,
                payload["status"].value,
            ))

    # A forward move into "completed" is logged to the timeline too (so the
    # delivery shows up), but needs no user-supplied reason — it carries a
    # system reason and is recorded separately from `tracked`.
    completing = (
        "status" in payload
        and payload["status"] == DeliverableStatus.completed
        and d.status != DeliverableStatus.completed
    )

    for field, value in payload.items():
        setattr(d, field, value)

    # Actual submission date: stamped with today's IST business date when the
    # deliverable is completed (unless one was given), cleared on a reversal.
    if completing and d.completion_date is None:
        d.completion_date = business_today()
    elif prev_status == DeliverableStatus.completed and d.status != DeliverableStatus.completed:
        d.completion_date = None

    for field_name, old_value, new_value in tracked:
        db.add(
            DeliverableChange(
                deliverable_id=d.id,
                field=field_name,
                old_value=old_value,
                new_value=new_value,
                changed_by=actor.id,
                # Optional: the column is NOT NULL, so "no reason" is stored as "".
                reason=reason or "",
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

    if completing:
        db.add(
            DeliverableChange(
                deliverable_id=d.id,
                field=DeliverableChangeField.STATUS,
                old_value=prev_status.value,
                new_value=DeliverableStatus.completed.value,
                changed_by=actor.id,
                reason="This activity has been delivered.",
            )
        )
        audit.record_audit(
            db,
            action=AuditAction.DELIVERABLE_FIELD_CHANGE,
            actor=actor,
            entity_type=EntityType.DELIVERABLE,
            entity_id=d.id,
            details={
                "field": DeliverableChangeField.STATUS,
                "old": prev_status.value,
                "new": DeliverableStatus.completed.value,
                "reason": "This activity has been delivered.",
            },
        )

    db.commit()
    db.refresh(d)
    _attach_owner_names(db, [d])
    _attach_can_manage([d], None)

    # Assignment notification: a (new) Assignee was set. Goes to the new
    # Assignee + the Head; clearing the Assignee sends nothing.
    if d.owner_employee_id and d.owner_employee_id != prev_owner:
        _notify_members(
            db,
            project,
            d,
            type_="deliverable_assigned",
            title="Deliverable Assigned",
            message=(
                "A deliverable has been assigned.\n"
                f"Project: {project.name}\n"
                f"Activity: {d.name}\n"
                f"Assignee: {_assignee_text(d)}\n"
                f"Planned Delivery Date: {_fmt(d.target_date)}"
            ),
        )

    # Schedule-change notification: the planned delivery (target) date moved.
    if "target_date" in payload and d.target_date != prev_target_date:
        _notify_members(
            db,
            project,
            d,
            type_="deliverable_date_updated",
            title="Delivery Date Updated",
            message=(
                "The planned delivery date for a deliverable has been updated.\n"
                f"Previous Date: {_fmt(prev_target_date)}\n"
                f"New Date: {_fmt(d.target_date)}"
            ),
        )

    # Completion notification: the deliverable was just marked completed.
    if (
        "status" in payload
        and d.status == DeliverableStatus.completed
        and prev_status != DeliverableStatus.completed
    ):
        _notify_members(
            db,
            project,
            d,
            type_="deliverable_completed",
            title="Deliverable Completed",
            message=(
                "A deliverable for your project has been marked as completed.\n"
                f"Project: {project.name}\n"
                f"Activity: {d.name}\n"
                f"Completion Date: {_fmt(d.completion_date or business_today())}"
            ),
        )
    return d


def get_deliverable(
    db: Session, actor: User, deliverable_id: uuid.UUID
) -> ProjectDeliverable:
    """Fetch a single deliverable by id (project resolved from the row)."""
    d = db.get(ProjectDeliverable, deliverable_id)
    if d is None:
        raise AppError("not_found", "Deliverable not found.", 404)
    project = _fetch_project(db, d.project_id)
    _assert_member(db, actor, project)
    _attach_owner_names(db, [d])
    _attach_project_names(db, [d])
    _attach_can_manage([d], None if _can_manage(db, actor, project) else set())
    return d


def list_deliverable_changes(
    db: Session, actor: User, deliverable_id: uuid.UUID
) -> list[DeliverableChange]:
    d = db.get(ProjectDeliverable, deliverable_id)
    if d is None:
        raise AppError("not_found", "Deliverable not found.", 404)
    project = _fetch_project(db, d.project_id)
    _assert_member(db, actor, project)

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
    project = _fetch_project(db, project_id)
    _assert_can_manage(db, actor, project)

    d = _fetch_deliverable(db, project_id, deliverable_id)
    db.delete(d)
    db.commit()
