"""Central per-project permission helper (Phase 2+).

Global JWT roles are only ``project_manager`` (PM) and ``employee``. Per-project
roles — Head, and (Phase 3) activity Lead/Contributor/QC — are resolved from the
DB per request here, so endpoints and services share one source of truth instead
of duplicating ``_assert_can_*`` checks across modules.

Phase 2 surface (this file): project-level view, project management, Head
assignment, and report review (PM + Head). Team leads no longer inherit
project-wide report access. Activity-level helpers (Head-manages / Lead-own-
activity) arrive in Phase 3.

Ownership chain: PM ⊃ Head for reads/review; PM performs project management and
Head assignment. These helpers are pure reads (no writes, no commits).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.projects.models import (
    ActivityMemberRole,
    Project,
    ProjectActivityMember,
    ProjectMember,
)
from app.modules.users.models import User, UserRole


def _actor_employee_id(db: Session, actor: User) -> uuid.UUID | None:
    """The caller's (non-deleted) employee id, or None if they have no profile."""
    return db.execute(
        select(Employee.id).where(
            Employee.user_id == actor.id, Employee.deleted_at.is_(None)
        )
    ).scalar_one_or_none()


def project_head_employee_id(db: Session, project_id: uuid.UUID) -> uuid.UUID | None:
    """The employee assigned as Head of the project, or None."""
    return db.execute(
        select(Project.head_employee_id).where(Project.id == project_id)
    ).scalar_one_or_none()


def is_project_head(db: Session, actor: User, project: Project) -> bool:
    """True when the caller is the project's Head."""
    if project.head_employee_id is None:
        return False
    emp_id = _actor_employee_id(db, actor)
    return emp_id is not None and emp_id == project.head_employee_id


def _is_project_member(db: Session, employee_id: uuid.UUID, project_id: uuid.UUID) -> bool:
    return db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        ).limit(1)
    ).scalar_one_or_none() is not None


def can_manage_project(db: Session, actor: User, project: Project) -> bool:
    """Create/edit/archive the project — PM only."""
    return actor.role == UserRole.project_manager


def can_assign_head(db: Session, actor: User, project: Project) -> bool:
    """Assign/replace the project Head — PM only."""
    return actor.role == UserRole.project_manager


def is_activity_lead(
    db: Session, actor: User, project_id: uuid.UUID, activity_id: uuid.UUID
) -> bool:
    """True when the caller is the assigned Lead of this specific activity."""
    emp_id = _actor_employee_id(db, actor)
    if emp_id is None:
        return False
    return db.execute(
        select(ProjectActivityMember.id).where(
            ProjectActivityMember.project_id == project_id,
            ProjectActivityMember.activity_id == activity_id,
            ProjectActivityMember.employee_id == emp_id,
            ProjectActivityMember.role == ActivityMemberRole.lead,
        ).limit(1)
    ).scalar_one_or_none() is not None


def leads_any_activity(db: Session, actor: User, project_id: uuid.UUID) -> bool:
    """True when the caller is the Lead of at least one activity in the project
    (used to gate the staffing UI / assignable-employee list for Leads)."""
    emp_id = _actor_employee_id(db, actor)
    if emp_id is None:
        return False
    return db.execute(
        select(ProjectActivityMember.id).where(
            ProjectActivityMember.project_id == project_id,
            ProjectActivityMember.employee_id == emp_id,
            ProjectActivityMember.role == ActivityMemberRole.lead,
        ).limit(1)
    ).scalar_one_or_none() is not None


def can_manage_activity_staffing(db: Session, actor: User, project: Project) -> bool:
    """Project-wide activity-staffing authority: PM (any project) or the project's
    Head. This is *full* control over every activity. A Lead's narrower per-activity
    authority is resolved by ``activity_staffing_authority`` — do not use this
    helper to gate a Lead's own-activity actions."""
    if actor.role == UserRole.project_manager:
        return True
    return is_project_head(db, actor, project)


def activity_staffing_authority(
    db: Session, actor: User, project: Project, activity_id: uuid.UUID
) -> str | None:
    """Resolve the caller's authority over ONE activity's staffing:

      "full"  -> PM or the project Head — may add/remove anyone in any role.
      "lead"  -> the assigned Lead of *this* activity — may add/remove
                 Contributors and QC on this activity only; may NOT touch the
                 Lead assignment or any other activity.
      None    -> not authorized to manage this activity's staffing.
    """
    if actor.role == UserRole.project_manager:
        return "full"
    if is_project_head(db, actor, project):
        return "full"
    if is_activity_lead(db, actor, project.id, activity_id):
        return "lead"
    return None


def can_view_project(db: Session, actor: User, project: Project) -> bool:
    """View the project — PM (any), the Head, or any project member."""
    if actor.role == UserRole.project_manager:
        return True
    emp_id = _actor_employee_id(db, actor)
    if emp_id is None:
        return False
    if project.head_employee_id is not None and emp_id == project.head_employee_id:
        return True
    return _is_project_member(db, emp_id, project.id)


def reviewable_project_ids(db: Session, actor: User) -> set[uuid.UUID]:
    """Projects whose reports the caller may review/see as a non-PM: those they
    Head, and only those. Team leads no longer inherit project-wide report
    access — a lead only manages staffing for their own activities and sees
    their own reports like any contributor.

    PM reviews every report and is handled by the caller, not enumerated here.
    """
    emp_id = _actor_employee_id(db, actor)
    if emp_id is None:
        return set()
    head_ids = db.execute(
        select(Project.id).where(
            Project.head_employee_id == emp_id,
            Project.deleted_at.is_(None),
        )
    ).scalars().all()
    return set(head_ids)


def can_review_report(db: Session, actor: User, project_ids: set[uuid.UUID]) -> bool:
    """Whether the caller may review (grant edit access on) a report whose lines
    touch ``project_ids``.

    Reviewers = PM (any report) or the **Head** of any of those projects. The
    "you cannot review your own report" rule is enforced by the caller, not here.
    """
    if actor.role == UserRole.project_manager:
        return True
    if not project_ids:
        return False
    return bool(set(project_ids) & reviewable_project_ids(db, actor))
