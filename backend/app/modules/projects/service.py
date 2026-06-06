"""Project service: RBAC-scoped reads + project_manager writes + membership.

RBAC (this module):
  project_manager  full access
  employee         read access, scoped to assigned projects only
"""
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.job_codes.models import JobCode
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from app.modules.projects.schemas import ProjectCreate, ProjectUpdate
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


def _push_notification(db: Session, user_id: uuid.UUID, type_: str, title: str,
                       message: str, entity_id: uuid.UUID | None = None,
                       target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="project", entity_id=entity_id, target_url=target_url)
        db.commit()
    except Exception:
        db.rollback()


_ALLOWED_TRANSITIONS: dict[ProjectStatus, set[ProjectStatus]] = {
    ProjectStatus.planning: {ProjectStatus.active, ProjectStatus.on_hold, ProjectStatus.completed},
    ProjectStatus.active: {ProjectStatus.on_hold, ProjectStatus.completed},
    ProjectStatus.on_hold: {ProjectStatus.active, ProjectStatus.completed},
    ProjectStatus.completed: {ProjectStatus.active},
    ProjectStatus.archived: {ProjectStatus.active},
}


def _alive():
    return select(Project).where(Project.deleted_at.is_(None))


def list_projects(
    db: Session,
    actor: User,
    *,
    q: str | None,
    status: ProjectStatus | None,
    employee_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[Project], int]:
    stmt = _alive()

    if actor.role == UserRole.employee:
        me = _current_employee(db, actor)
        if me is None:
            return [], 0
        stmt = stmt.where(
            Project.id.in_(
                select(ProjectMember.project_id).where(ProjectMember.employee_id == me.id)
            )
        )
    # project_manager: full access, no scope filter

    if status is not None:
        stmt = stmt.where(Project.status == status)
    else:
        stmt = stmt.where(Project.status != ProjectStatus.archived)

    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                Project.code.ilike(like),
                Project.name.ilike(like),
                Project.client.ilike(like),
            )
        )
    if employee_id is not None:
        stmt = stmt.where(
            Project.id.in_(
                select(ProjectMember.project_id).where(
                    ProjectMember.employee_id == employee_id
                )
            )
        )

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(stmt.order_by(Project.created_at.desc()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    projects = list(rows)
    _attach_member_counts(db, projects)
    _attach_job_codes(db, projects)
    return projects, total


def _attach_job_codes(db: Session, projects: list[Project]) -> None:
    """Bulk-fetch job codes and attach code/name to project instances."""
    jc_ids = {p.job_code_id for p in projects if p.job_code_id}
    if not jc_ids:
        for p in projects:
            p.job_code_code = None   # type: ignore[attr-defined]
            p.job_code_name = None   # type: ignore[attr-defined]
        return
    rows = db.execute(
        select(JobCode).where(JobCode.id.in_(jc_ids))
    ).scalars().all()
    by_id = {jc.id: jc for jc in rows}
    for p in projects:
        jc = by_id.get(p.job_code_id) if p.job_code_id else None
        p.job_code_code = jc.code if jc else None   # type: ignore[attr-defined]
        p.job_code_name = jc.name if jc else None   # type: ignore[attr-defined]


def _attach_member_counts(db: Session, projects: list[Project]) -> None:
    ids = [p.id for p in projects]
    counts: dict[uuid.UUID, int] = {}
    if ids:
        for pid, c in db.execute(
            select(ProjectMember.project_id, func.count())
            .where(ProjectMember.project_id.in_(ids))
            .group_by(ProjectMember.project_id)
        ).all():
            counts[pid] = c
    for p in projects:
        p.member_count = counts.get(p.id, 0)  # type: ignore[attr-defined]


def _assert_can_read(db: Session, actor: User, project: Project) -> None:
    if actor.role == UserRole.project_manager:
        return
    if actor.role == UserRole.employee:
        me = _current_employee(db, actor)
        if me is not None and db.execute(
            select(ProjectMember.id).where(
                ProjectMember.project_id == project.id,
                ProjectMember.employee_id == me.id,
            )
        ).first():
            return
        raise AppError("forbidden", "You can only view projects you're assigned to.", 403)
    raise AppError("forbidden", "Not permitted.", 403)


def _fetch(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return project


def get_project(db: Session, actor: User, project_id: uuid.UUID) -> Project:
    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)
    project.member_count = db.execute(  # type: ignore[attr-defined]
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    ).scalar_one()
    _attach_job_codes(db, [project])
    return project


def _validate_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise AppError("validation_error", "End date cannot be before start date.", 422)


def _resolve_job_code(
    db: Session, raw: str | None, project_name: str, actor_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Map a free-text job code to a JobCode id.

    Reuses an existing active job code when one matches (case-insensitive),
    otherwise creates a new active job code on the fly so PM-entered codes
    flow through the same master-data join used by reports and project views.
    """
    if raw is None:
        return None
    code = raw.strip()
    if code == "":
        return None
    if len(code) > 30:
        raise AppError("validation_error", "Job code must be 30 characters or fewer.", 422)
    existing = db.execute(
        select(JobCode).where(
            func.lower(JobCode.code) == code.lower(),
            JobCode.is_active.is_(True),
        )
    ).scalars().first()
    if existing is not None:
        return existing.id
    jc = JobCode(code=code, name=(project_name or code)[:200], created_by=actor_id)
    db.add(jc)
    db.flush()
    return jc.id


def create_project(db: Session, actor: User, data: ProjectCreate) -> Project:
    if db.execute(
        select(Project).where(Project.code == data.code, Project.deleted_at.is_(None))
    ).scalar_one_or_none():
        raise AppError("conflict", "A project with this code already exists.", 409)
    _validate_dates(data.start_date, data.end_date)

    payload = data.model_dump()
    job_code_id = _resolve_job_code(db, payload.pop("job_code", None), data.name, actor.id)
    project = Project(
        **payload, job_code_id=job_code_id, created_by=actor.id, updated_by=actor.id
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Project violates a uniqueness constraint.", 409)
    db.refresh(project)
    project.member_count = 0  # type: ignore[attr-defined]
    _attach_job_codes(db, [project])
    return project


def _validate_status_transition(current: ProjectStatus, new: ProjectStatus) -> None:
    if new == current:
        return
    if new == ProjectStatus.archived:
        raise AppError("validation_error", "Use delete to archive a project.", 422)
    if new not in _ALLOWED_TRANSITIONS[current]:
        raise AppError(
            "validation_error",
            f"Invalid status transition from {current.value} to {new.value}.",
            422,
        )


def update_project(
    db: Session, actor: User, project_id: uuid.UUID, data: ProjectUpdate
) -> Project:
    project = _fetch(db, project_id)
    fields = data.model_dump(exclude_unset=True)

    if "status" in fields and fields["status"] is not None:
        _validate_status_transition(project.status, fields["status"])

    new_start = fields.get("start_date", project.start_date)
    new_end = fields.get("end_date", project.end_date)
    _validate_dates(new_start, new_end)

    if "job_code" in fields:
        new_name = fields.get("name") or project.name
        fields["job_code_id"] = _resolve_job_code(
            db, fields.pop("job_code"), new_name, actor.id
        )

    for key, value in fields.items():
        setattr(project, key, value)
    project.updated_by = actor.id
    db.add(project)
    db.commit()
    db.refresh(project)
    project.member_count = db.execute(  # type: ignore[attr-defined]
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    ).scalar_one()
    _attach_job_codes(db, [project])
    return project


def archive_project(db: Session, actor: User, project_id: uuid.UUID) -> None:
    project = _fetch(db, project_id)
    project.status = ProjectStatus.archived
    project.updated_by = actor.id
    db.add(project)
    db.commit()


def list_members(db: Session, actor: User, project_id: uuid.UUID) -> list[ProjectMember]:
    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)
    rows = db.execute(
        select(ProjectMember, Employee)
        .join(Employee, Employee.id == ProjectMember.employee_id)
        .where(ProjectMember.project_id == project_id)
        .order_by(ProjectMember.role, Employee.first_name)
    ).all()
    members: list[ProjectMember] = []
    for member, employee in rows:
        member.employee_name = employee.full_name  # type: ignore[attr-defined]
        members.append(member)
    return members


def _demote_existing_lead(
    db: Session, project_id: uuid.UUID, except_id: uuid.UUID | None = None
) -> None:
    leads = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.role == ProjectMemberRole.team_lead,
        )
    ).scalars().all()
    for lead in leads:
        if except_id is not None and lead.id == except_id:
            continue
        lead.role = ProjectMemberRole.contributor
        db.add(lead)


def add_member(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    employee_id: uuid.UUID,
    role: ProjectMemberRole,
) -> ProjectMember:
    project = _fetch(db, project_id)
    if project.status == ProjectStatus.archived:
        raise AppError("validation_error", "Cannot assign to an archived project.", 422)

    employee = db.get(Employee, employee_id)
    if employee is None or employee.deleted_at is not None:
        raise AppError("validation_error", "Employee not found.", 422)
    if employee.status != EmployeeStatus.active:
        raise AppError("validation_error", "Employee is not active.", 422)

    if db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        )
    ).scalar_one_or_none():
        raise AppError("conflict", "Employee is already assigned to this project.", 409)

    if role == ProjectMemberRole.team_lead:
        _demote_existing_lead(db, project_id)

    member = ProjectMember(
        project_id=project_id, employee_id=employee_id, role=role, created_by=actor.id
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    member.employee_name = employee.full_name  # type: ignore[attr-defined]
    if employee.user_id is not None:
        _push_notification(
            db, employee.user_id, "project_assigned",
            f"You were assigned to {project.name}",
            f"You have been added to project {project.name} ({project.code}) as {role.value}.",
            project.id,
            f"/projects/{project.id}",
        )
    return member


def update_member_role(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    employee_id: uuid.UUID,
    role: ProjectMemberRole,
) -> ProjectMember:
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise AppError("not_found", "Membership not found.", 404)

    if role == ProjectMemberRole.team_lead:
        _demote_existing_lead(db, project_id, except_id=member.id)
    member.role = role
    db.add(member)
    db.commit()
    db.refresh(member)
    employee = db.get(Employee, employee_id)
    member.employee_name = employee.full_name if employee else ""  # type: ignore[attr-defined]
    return member


def remove_member(
    db: Session, actor: User, project_id: uuid.UUID, employee_id: uuid.UUID
) -> None:
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise AppError("not_found", "Membership not found.", 404)
    db.delete(member)
    db.commit()
