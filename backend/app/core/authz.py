"""Central per-project permission helper (Phase 2+).

Global JWT roles are only ``project_manager`` (PM) and ``employee``. Per-project
roles — Head, and (Phase 3) activity Lead/Contributor/QC — are resolved from the
DB per request here, so endpoints and services share one source of truth instead
of duplicating ``_assert_can_*`` checks across modules.

Phase 2 surface (this file): project-level view, project management, Head
assignment, and report review (PM + Head, with the legacy ``team_lead`` reviewer
path kept until Phase 6). Activity-level helpers (Head-manages / Lead-own-
activity) arrive in Phase 3.

Ownership chain: PM ⊃ Head for reads/review; PM performs project management and
Head assignment. These helpers are pure reads (no writes, no commits).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.projects.models import Project, ProjectMember, ProjectMemberRole
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


def can_review_report(db: Session, actor: User, project_ids: set[uuid.UUID]) -> bool:
    """Whether the caller may review (reject / request-edit / grant-edit) a report
    whose lines touch ``project_ids``.

    Reviewers = PM (any report), the **Head** of any of those projects, or
    (legacy, until Phase 6) a ``team_lead`` on any of those projects. The
    "you cannot review your own report" rule is enforced by the caller, not here.
    """
    if actor.role == UserRole.project_manager:
        return True
    if not project_ids:
        return False
    emp_id = _actor_employee_id(db, actor)
    if emp_id is None:
        return False
    # Head of any of the report's projects.
    is_head = db.execute(
        select(Project.id).where(
            Project.id.in_(project_ids),
            Project.head_employee_id == emp_id,
        ).limit(1)
    ).scalar_one_or_none() is not None
    if is_head:
        return True
    # Legacy team_lead reviewer path (retired in Phase 6).
    return db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id.in_(project_ids),
            ProjectMember.employee_id == emp_id,
            ProjectMember.role == ProjectMemberRole.team_lead,
        ).limit(1)
    ).scalar_one_or_none() is not None
