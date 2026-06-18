"""Project activity service — Phase B Deliverable Activity Tracker.

RBAC:
  project_manager  — full CRUD on all activities in the project
  team_lead        — read + update status/remarks (cannot create or delete)
  contributor/qc   — read only
  non-member       — 403
"""
import uuid
from datetime import timezone, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.activity_types.models import ActivityType
from app.modules.employees.models import Employee
from app.modules.project_activities.models import ProjectActivity, VALID_ACTIVITY_STATUSES
from app.modules.project_activities.schemas import ProjectActivityCreate, ProjectActivityUpdate
from app.modules.projects.models import Project, ProjectMember, ProjectMemberRole
from app.modules.users.models import User, UserRole
from app.modules.employees.service import _current_employee
from app.shared.errors import AppError


# ── helpers ──────────────────────────────────────────────────────────────────

def _fetch_project(db: Session, project_id: uuid.UUID) -> Project:
    p = db.get(Project, project_id)
    if p is None or p.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return p


def _fetch_activity(
    db: Session, project_id: uuid.UUID, activity_id: uuid.UUID
) -> ProjectActivity:
    a = db.get(ProjectActivity, activity_id)
    if a is None or a.project_id != project_id:
        raise AppError("not_found", "Activity not found.", 404)
    return a


def _member_role(db: Session, actor: User, project: Project) -> ProjectMemberRole | None:
    """Return the actor's ProjectMemberRole for this project, or None if not a member."""
    me = _current_employee(db, actor)
    if me is None:
        return None
    row = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.employee_id == me.id,
        )
    ).scalar_one_or_none()
    return row.role if row else None


def _assert_can_read(db: Session, actor: User, project: Project) -> None:
    if actor.role == UserRole.project_manager:
        return
    role = _member_role(db, actor, project)
    if role is None:
        raise AppError("forbidden", "You must be a project member to view activities.", 403)


def _assert_pm(actor: User) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Only project managers can perform this action.", 403)


def _assert_can_edit(db: Session, actor: User, project: Project) -> bool:
    """Return True if PM (full edit), False if team_lead (limited edit), raise 403 otherwise."""
    if actor.role == UserRole.project_manager:
        return True
    role = _member_role(db, actor, project)
    if role == ProjectMemberRole.team_lead:
        return False
    raise AppError("forbidden", "Only project managers and team leads can update activities.", 403)


def _resolve_activity_type(db: Session, at_id: uuid.UUID | None) -> tuple[uuid.UUID | None, str | None]:
    if at_id is None:
        return None, None
    at = db.get(ActivityType, at_id)
    if at is None or not at.is_active:
        raise AppError("validation_error", "Activity type not found or inactive.", 422)
    return at.id, at.name


def _resolve_assignee(db: Session, emp_id: uuid.UUID | None) -> tuple[uuid.UUID | None, str | None]:
    if emp_id is None:
        return None, None
    emp = db.get(Employee, emp_id)
    if emp is None or emp.deleted_at is not None:
        raise AppError("validation_error", "Employee not found.", 422)
    return emp.id, emp.full_name


# ── public API ────────────────────────────────────────────────────────────────

def list_activities(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProjectActivity]:
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)
    return list(
        db.execute(
            select(ProjectActivity)
            .where(ProjectActivity.project_id == project_id)
            .order_by(ProjectActivity.sort_order, ProjectActivity.created_at)
        ).scalars().all()
    )


def create_activity(
    db: Session, actor: User, project_id: uuid.UUID, data: ProjectActivityCreate
) -> ProjectActivity:
    _assert_pm(actor)
    _fetch_project(db, project_id)

    if data.status not in VALID_ACTIVITY_STATUSES:
        raise AppError("validation_error", f"Invalid status '{data.status}'.", 422)

    at_id, at_name = _resolve_activity_type(db, data.activity_type_id)
    emp_id, emp_name = _resolve_assignee(db, data.assigned_to_id)

    activity = ProjectActivity(
        project_id=project_id,
        activity_type_id=at_id,
        activity_type_name=at_name,
        title=data.title,
        status=data.status,
        assigned_to_id=emp_id,
        assigned_to_name=emp_name,
        target_date=data.target_date,
        closed_date=data.closed_date,
        remarks=data.remarks,
        sort_order=data.sort_order,
        created_by=actor.id,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def update_activity(
    db: Session, actor: User, project_id: uuid.UUID,
    activity_id: uuid.UUID, data: ProjectActivityUpdate
) -> ProjectActivity:
    project = _fetch_project(db, project_id)
    is_pm = _assert_can_edit(db, actor, project)
    activity = _fetch_activity(db, project_id, activity_id)

    fields = data.model_dump(exclude_unset=True)

    if not is_pm:
        # Team lead may only update status and remarks
        allowed = {"status", "remarks"}
        disallowed = set(fields.keys()) - allowed
        if disallowed:
            raise AppError(
                "forbidden",
                "Team leads can only update status and remarks.",
                403,
            )

    if "status" in fields and fields["status"] not in VALID_ACTIVITY_STATUSES:
        raise AppError("validation_error", f"Invalid status '{fields['status']}'.", 422)

    # Auto-set closed_date when status transitions to closed
    if fields.get("status") == "closed" and activity.status != "closed":
        if "closed_date" not in fields:
            fields["closed_date"] = datetime.now(timezone.utc).date()

    # Clear closed_date when re-opening
    if fields.get("status") in ("open", "in_progress") and activity.status == "closed":
        if "closed_date" not in fields:
            fields["closed_date"] = None

    if "activity_type_id" in fields:
        at_id, at_name = _resolve_activity_type(db, fields.pop("activity_type_id"))
        fields["activity_type_id"] = at_id
        fields["activity_type_name"] = at_name

    if "assigned_to_id" in fields:
        emp_id, emp_name = _resolve_assignee(db, fields.pop("assigned_to_id"))
        fields["assigned_to_id"] = emp_id
        fields["assigned_to_name"] = emp_name

    for key, value in fields.items():
        setattr(activity, key, value)

    activity.updated_at = datetime.now(timezone.utc)
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return activity


def delete_activity(
    db: Session, actor: User, project_id: uuid.UUID, activity_id: uuid.UUID
) -> None:
    _assert_pm(actor)
    _fetch_project(db, project_id)
    activity = _fetch_activity(db, project_id, activity_id)
    db.delete(activity)
    db.commit()
