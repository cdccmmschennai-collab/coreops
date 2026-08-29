"""Project service: RBAC-scoped reads + project_manager writes + membership.

RBAC (this module):
  project_manager  full access
  employee         read access, scoped to assigned projects only
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.job_codes.models import JobCode
from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.modules.projects.models import (
    ActivityMemberRole,
    Project,
    ProjectActivityMember,
    ProjectMember,
    ProjectMemberRole,
    ProjectPlannedDateChange,
    ProjectStatus,
    ProjectTagScopeRevision,
    ProjectTimelineEvent,
    SCOPE_TYPE_TAG_BASED,
    TimelineEventType,
    VALID_TAG_SCOPE_STATUSES,
)
from app.modules.projects.schemas import (
    ActivityMemberCreate,
    ActivityMemberOut,
    ActivityMemberUpdate,
    ActivityStaffingOut,
    LedProject,
    LedProjectMember,
    PlannedDateUpdate,
    ProjectCreate,
    ProjectSummaryOut,
    ProjectUpdate,
    TagScopeOut,
    TagScopeProgressRow,
    TagScopeRevisionOut,
    TagScopeUpdate,
)
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


def _actor_display_name(db: Session, actor: User) -> str:
    """Human name of the assigner for the notification body — their employee
    full name if they have a profile, else their login email."""
    emp = db.execute(
        select(Employee).where(
            Employee.user_id == actor.id, Employee.deleted_at.is_(None)
        )
    ).scalars().first()
    return emp.full_name if emp is not None else actor.email


def _assignment_role_label(role: ActivityMemberRole, is_qc: bool) -> str:
    """The single role word shown in the assignment notification. QC is an
    additive flag, but for the notification we surface it as the role when the
    member holds no higher (Lead) role — matching the trigger list which treats
    'assign QC' as its own event."""
    if role == ActivityMemberRole.lead:
        return "Lead"
    if is_qc:
        return "QC"
    return "Contributor"


def _notify_assignment(
    db: Session,
    *,
    assignee: Employee,
    actor: User,
    project: Project,
    role_label: str,
    activity_name: str | None,
) -> None:
    """Create the in-app 'You have been assigned to a project' notification for
    the assigned employee only. Never notifies the assigner. Best-effort: a
    notification failure must not roll back the assignment (already committed),
    so it manages its own commit/rollback like ``_push_notification``.

    ``activity_name`` is omitted for a Head (the Head belongs to the project, not
    a specific activity)."""
    # No login row -> nowhere to deliver; and never notify the assigner.
    if assignee.user_id is None or assignee.user_id == actor.id:
        return
    lines = [
        "Project:", project.name, "",
        "Code:", project.code, "",
        "Role:", role_label, "",
    ]
    if activity_name is not None:
        lines += ["Activity:", activity_name, ""]
    lines += ["Assigned by:", _actor_display_name(db, actor)]
    _push_notification(
        db,
        assignee.user_id,
        "project_assigned",
        "You have been assigned to a project",
        "\n".join(lines),
        project.id,
        f"/projects/{project.id}",
    )


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
        # Visible to an employee when they are the Head or a member of the project.
        stmt = stmt.where(
            or_(
                Project.head_employee_id == me.id,
                Project.id.in_(
                    select(ProjectMember.project_id).where(ProjectMember.employee_id == me.id)
                ),
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
    _attach_maintenance_plants(db, projects)
    _attach_heads(db, projects)
    for p in projects:
        p.days_running = _compute_days_running(p)  # type: ignore[attr-defined]
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


def _attach_maintenance_plants(db: Session, projects: list[Project]) -> None:
    """Bulk-fetch plant info and attach the flattened code/description fields,
    same pattern as _attach_job_codes.

    Planning Plant precedence: the project's direct planning_plant_id (project
    master link) wins; if absent we fall back to the parent Planning Plant of
    the legacy maintenance_plant_id. Maintenance Plant fields come only from
    maintenance_plant_id and are null for project-master rows (the Maintenance
    Plant is chosen at usage time, not stored on the project)."""
    # Direct Planning Plant link (project master).
    pp_ids = {p.planning_plant_id for p in projects if p.planning_plant_id}
    planning_by_id: dict = {}
    if pp_ids:
        planning_by_id = {
            pp.id: pp for pp in db.execute(
                select(PlanningPlant).where(PlanningPlant.id.in_(pp_ids))
            ).scalars().all()
        }

    # Legacy direct Maintenance Plant link (+ its parent Planning Plant).
    mp_ids = {p.maintenance_plant_id for p in projects if p.maintenance_plant_id}
    mp_by_id: dict = {}
    if mp_ids:
        rows = db.execute(
            select(MaintenancePlant, PlanningPlant)
            .join(PlanningPlant, MaintenancePlant.planning_plant_id == PlanningPlant.id)
            .where(MaintenancePlant.id.in_(mp_ids))
        ).all()
        mp_by_id = {mp.id: (mp, pp) for mp, pp in rows}

    for p in projects:
        mp, mp_pp = mp_by_id.get(p.maintenance_plant_id, (None, None)) if p.maintenance_plant_id else (None, None)
        pp = planning_by_id.get(p.planning_plant_id) if p.planning_plant_id else None
        pp = pp or mp_pp   # direct link wins, else the maintenance plant's parent
        p.maintenance_plant_code = mp.code if mp else None   # type: ignore[attr-defined]
        p.maintenance_plant_description = mp.description if mp else None   # type: ignore[attr-defined]
        p.planning_plant_code = pp.code if pp else None   # type: ignore[attr-defined]
        p.planning_plant_description = pp.description if pp else None   # type: ignore[attr-defined]


def _attach_heads(db: Session, projects: list[Project]) -> None:
    """Bulk-fetch each project's Head employee name (Phase 2), same pattern as
    _attach_job_codes. head_employee_name is null when no Head is assigned."""
    head_ids = {p.head_employee_id for p in projects if p.head_employee_id}
    by_id: dict = {}
    if head_ids:
        by_id = {
            e.id: e for e in db.execute(
                select(Employee).where(Employee.id.in_(head_ids))
            ).scalars().all()
        }
    for p in projects:
        emp = by_id.get(p.head_employee_id) if p.head_employee_id else None
        p.head_employee_name = emp.full_name if emp else None  # type: ignore[attr-defined]


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
    # PM, the Head, or any project member (visibility backbone). Head is honored
    # even without a membership row (authz checks head_employee_id directly).
    if not authz.can_view_project(db, actor, project):
        raise AppError("forbidden", "You can only view projects you're assigned to.", 403)


def _fetch(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return project


def get_project(db: Session, actor: User, project_id: uuid.UUID) -> Project:
    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)
    return _decorate_project(db, project)


def _ensure_project_member(
    db: Session, project_id: uuid.UUID, employee_id: uuid.UUID, actor: User
) -> None:
    """Idempotently give the employee a project_members visibility row.

    The visibility backbone (spec 4.3) keeps every project-scoped read query
    working: any assignment (Head here, activity members in Phase 3) implies a
    member row. Role is `contributor` — the Head's authority comes from
    `projects.head_employee_id`, not from this row.
    """
    exists = db.execute(
        select(ProjectMember.id).where(
            ProjectMember.project_id == project_id,
            ProjectMember.employee_id == employee_id,
        ).limit(1)
    ).scalar_one_or_none()
    if exists is None:
        db.add(ProjectMember(
            project_id=project_id,
            employee_id=employee_id,
            role=ProjectMemberRole.contributor,
            created_by=actor.id,
        ))


def _prune_project_member(db: Session, project: Project, employee_id: uuid.UUID) -> None:
    """Reference-counted teardown of the visibility backbone — the mirror of
    ``_ensure_project_member``.

    Drops the employee's project_members row once they hold no remaining
    assignment on the project (no activity staffing and not the Head). Auto-added
    member rows only ever came from an assignment, so removing the last one must
    remove the row; otherwise member_count would keep counting people who are no
    longer assigned. Employees added directly via the /members endpoint are
    removed by that endpoint, not here. Callers must have already deleted the
    assignment being removed; we flush so that pending delete is excluded from
    the "still staffed" check below (the session runs with autoflush off).
    """
    if project.head_employee_id == employee_id:
        return
    db.flush()
    still_staffed = db.execute(
        select(ProjectActivityMember.id)
        .where(
            ProjectActivityMember.project_id == project.id,
            ProjectActivityMember.employee_id == employee_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if still_staffed is not None:
        return
    member = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project.id,
            ProjectMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is not None:
        db.delete(member)


def set_project_head(
    db: Session, actor: User, project_id: uuid.UUID, head_employee_id: uuid.UUID | None
) -> Project:
    """PM assigns, replaces, or clears (null) the project Head.

    Auto-maintains the visibility backbone (adds the new Head as a project
    member); the prior Head's member row is reference-counted away unless they
    remain assigned via an activity. Emits a timeline event. Does NOT touch
    notification routing (Phase 4).
    """
    project = _fetch(db, project_id)
    if not authz.can_assign_head(db, actor, project):
        raise AppError("forbidden", "Only project managers can assign the project Head.", 403)

    if head_employee_id is not None:
        employee = db.get(Employee, head_employee_id)
        if employee is None or employee.deleted_at is not None:
            raise AppError("validation_error", "Employee not found.", 422)
        if employee.status != EmployeeStatus.active:
            raise AppError("validation_error", "The Head must be an active employee.", 422)

    previous = project.head_employee_id
    if previous == head_employee_id:
        return _decorate_project(db, project)   # idempotent — no event, no change

    previous_name = None
    if previous is not None:
        prev_emp = db.get(Employee, previous)
        previous_name = prev_emp.full_name if prev_emp else None

    project.head_employee_id = head_employee_id
    db.add(project)
    if head_employee_id is not None:
        _ensure_project_member(db, project_id, head_employee_id, actor)
    # Drop the prior Head's auto-added visibility row unless they remain assigned
    # via an activity, so replacing/clearing the Head doesn't inflate the count.
    if previous is not None:
        _prune_project_member(db, project, previous)
    _record_timeline(
        db,
        project_id,
        TimelineEventType.HEAD_ASSIGNED if previous is None else TimelineEventType.HEAD_CHANGED,
        actor,
        {
            "head_employee_id": str(head_employee_id) if head_employee_id else None,
            "head_employee_name": employee.full_name if head_employee_id is not None else None,
            "previous_head_employee_id": str(previous) if previous else None,
            "previous_head_employee_name": previous_name,
        },
    )
    db.commit()
    db.refresh(project)
    # Notify the newly assigned Head (not on a clear). Head belongs to the whole
    # project, so no Activity line.
    if head_employee_id is not None:
        _notify_assignment(
            db,
            assignee=employee,
            actor=actor,
            project=project,
            role_label="Head",
            activity_name=None,
        )
    return _decorate_project(db, project)


def _decorate_project(db: Session, project: Project) -> Project:
    """Attach the read-only display fields the ProjectOut schema expects."""
    project.member_count = db.execute(  # type: ignore[attr-defined]
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    ).scalar_one()
    _attach_job_codes(db, [project])
    _attach_maintenance_plants(db, [project])
    _attach_heads(db, [project])
    project.days_running = _compute_days_running(project)  # type: ignore[attr-defined]
    return project


def _validate_dates(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and end < start:
        raise AppError("validation_error", "Planned completion date cannot be before start date.", 422)


def _compute_days_running(project: Project) -> int | None:
    if project.start_date is None:
        return None
    return (datetime.now(timezone.utc).date() - project.start_date).days


def _record_timeline(
    db: Session,
    project_id: uuid.UUID,
    event_type: str,
    actor: User,
    details: dict | None = None,
) -> None:
    """Stage a timeline event in the current session. Caller must commit."""
    event = ProjectTimelineEvent(
        project_id=project_id,
        event_type=event_type,
        actor_id=actor.id,
        actor_name=actor.email,
        details=details or {},
    )
    db.add(event)


def _record_activity_staffing_event(
    db: Session,
    project_id: uuid.UUID,
    event_type: str,
    actor: User,
    employee: Employee,
    activity,
) -> None:
    """Stage a per-activity staffing timeline event (Lead/Contributor/QC add or
    remove). Stores the employee name and the activity code/name so the timeline
    can render a readable line without a follow-up lookup. Caller must commit."""
    _record_timeline(db, project_id, event_type, actor, {
        "employee_name": employee.full_name,
        "activity_code": activity.code if activity else None,
        "activity_name": activity.name if activity else None,
    })


def _assert_can_view_timeline(db: Session, actor: User, project: Project) -> None:
    """PM, the project Head, or any project member can view the timeline.
    (Phase 2 Task 5 relaxes the earlier team-lead-only member rule to all
    members; PM + Head visibility is unchanged. Same rule as project read.)"""
    if not authz.can_view_project(db, actor, project):
        raise AppError(
            "forbidden",
            "Only project managers, the Head, and project members can view the timeline.",
            403,
        )


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
    # No code at all (migration 0078) is never a conflict — any number of
    # no-code projects can coexist, same as the partial-unique index itself
    # allows (Postgres NULL <> NULL). `Project.code == None` would otherwise
    # compile to "code IS NULL" and match every other no-code project.
    if data.code and db.execute(
        select(Project).where(Project.code == data.code, Project.deleted_at.is_(None))
    ).scalar_one_or_none():
        raise AppError("conflict", "A project with this code already exists.", 409)
    _validate_dates(data.start_date, data.planned_completion_date)

    payload = data.model_dump()
    job_code_id = _resolve_job_code(db, payload.pop("job_code", None), data.name, actor.id)
    project = Project(
        **payload, job_code_id=job_code_id, created_by=actor.id, updated_by=actor.id
    )
    db.add(project)
    try:
        db.flush()  # obtain project.id before adding timeline event
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Project violates a uniqueness constraint.", 409)
    _record_timeline(db, project.id, TimelineEventType.PROJECT_CREATED, actor, {
        "project_name": project.name,
        "code": project.code,
    })
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "Project violates a uniqueness constraint.", 409)
    db.refresh(project)
    project.member_count = 0  # type: ignore[attr-defined]
    project.days_running = _compute_days_running(project)  # type: ignore[attr-defined]
    _attach_job_codes(db, [project])
    _attach_maintenance_plants(db, [project])
    _attach_heads(db, [project])
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


_UNSET = object()


# --------------------------------------------------------------------------
# Project tag scope (Phase 3 data foundation + Phase 4 managed workflow)
#
# Phase 3 established the columns, the append-only revision table, the read and
# the recording primitive. Phase 4 adds the managed write workflow on top:
# PUT /projects/{id}/tag-scope, optimistic concurrency, the no-op rule and the
# reason policy. Nothing here reads Daily Reports, benchmarks or Activity
# Master, and nothing computes progress.
# --------------------------------------------------------------------------


# Substituted when the very first estimate is saved without a reason. Revising
# an existing scope always requires the author to say why (see below).
INITIAL_SCOPE_REASON = "Initial project estimate"


# --------------------------------------------------------------------------
# Turning tag scope off (TAG_BASED -> NONE)
#
# There is no guard here, and that is the whole design. Reclassifying a project
# back to NONE is a DEACTIVATION, not a deletion:
#
#   nothing is written   projects.estimated_tag_count, tag_scope_status,
#                        tag_scope_revision and every project_tag_scope_revisions
#                        row are left exactly as they are. No revision is minted
#                        either - flipping the feature off is not a scope
#                        decision, and history records decisions (1200 -> 1500),
#                        not toggles.
#
#   nothing enforces     every consumer of tag scope already asks
#                        `project.scope_type == TAG_BASED` before it does
#                        anything (tag_progress.project_tag_capacity, which the
#                        Daily Report cap and the Summary both go through, and
#                        record_tag_scope_revision below). Setting NONE therefore
#                        removes the cap, empties the Summary's progress rows and
#                        closes the scope-management surface in one assignment,
#                        with no second switch to keep in step.
#
#   nothing is rewritten reported tag counts on existing work reports are
#                        untouched; an employee simply stops being measured
#                        against a project ceiling.
#
# Switching back to TAG_BASED restores the preserved estimate, status, revision
# number and full history unchanged - there is no reset step to undo, and no
# duplicate rows, because nothing was ever removed.
#
# An earlier build refused this transition ("...cannot be changed to a non-tag
# project without first resolving the existing scope"). That protected the audit
# trail by making a legitimate business change impossible; preserving the trail
# while ignoring it is strictly better.
# --------------------------------------------------------------------------


def _assert_can_read_tag_scope(db: Session, actor: User, project: Project) -> None:
    """Reading tag scope is open to anyone who may view the project.

    The scope and its history are context every contributor needs — how many
    tags the project covers, and why that number changed. Read and write are
    deliberately split: CHANGING the scope stays PM or THIS project's Head (see
    record_tag_scope_revision), so a member sees the numbers without being able
    to move them.
    """
    _assert_can_read(db, actor, project)


def get_tag_scope(db: Session, actor: User, project_id: uuid.UUID) -> TagScopeOut:
    """Current scope plus its full revision history, newest revision last."""
    project = _fetch(db, project_id)
    _assert_can_read_tag_scope(db, actor, project)

    rows = db.execute(
        select(ProjectTagScopeRevision)
        .where(ProjectTagScopeRevision.project_id == project_id)
        .order_by(ProjectTagScopeRevision.revision)
    ).scalars().all()

    # Resolve actor names in one pass (same join style as _attach_* helpers).
    user_ids = {r.changed_by for r in rows}
    if project.tag_scope_updated_by is not None:
        user_ids.add(project.tag_scope_updated_by)
    names: dict[uuid.UUID, str] = {}
    if user_ids:
        for uid, email, first, last in db.execute(
            select(User.id, User.email, Employee.first_name, Employee.last_name)
            .outerjoin(Employee, (Employee.user_id == User.id) & (Employee.deleted_at.is_(None)))
            .where(User.id.in_(user_ids))
        ).all():
            names[uid] = f"{first} {last}".strip() if first else email

    revisions = []
    for r in rows:
        out = TagScopeRevisionOut.model_validate(r)
        out.changed_by_name = names.get(r.changed_by, "")
        revisions.append(out)

    return TagScopeOut(
        project_id=project.id,
        scope_type=project.scope_type,
        estimated_tag_count=project.estimated_tag_count,
        tag_scope_status=project.tag_scope_status,
        tag_scope_revision=project.tag_scope_revision,
        tag_scope_updated_at=project.tag_scope_updated_at,
        tag_scope_updated_by=project.tag_scope_updated_by,
        tag_scope_updated_by_name=(
            names.get(project.tag_scope_updated_by)
            if project.tag_scope_updated_by is not None
            else None
        ),
        revisions=revisions,
    )


def get_project_summary(db: Session, actor: User, project_id: uuid.UUID) -> ProjectSummaryOut:
    """Summary tab payload. Readable by anyone who may view the project — unlike
    the Tag Scope tab, this is a progress view, not scope administration."""
    from app.modules.projects import tag_progress

    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)
    return ProjectSummaryOut(
        project_id=project.id,
        scope_type=project.scope_type,
        estimated_tag_count=project.estimated_tag_count,
        tag_scope_status=project.tag_scope_status,
        tag_progress=[
            TagScopeProgressRow(**row) for row in tag_progress.project_tag_progress(db, project)
        ],
    )


def _assert_can_read_weekly_report(db: Session, actor: User, project: Project) -> None:
    """Weekly Report access — THIS project's assigned Head, and nobody else.

    Narrower than every other tab on the page on purpose, and narrower than
    ``can_edit_project``: a PM is NOT included. The current requirement is that
    the weekly operational report belongs to the Head who runs the project; if
    PM access is wanted later it is one clause here, not a re-plumbing.

    Head authority is per-project by construction — ``authz.is_project_head``
    compares the caller's employee id against THIS project's head_employee_id,
    so heading project A grants nothing on project B. This is the same helper
    the Tag Scope write path and the Edit rule use; no second role rule exists.
    """
    if not authz.is_project_head(db, actor, project):
        raise AppError(
            "forbidden",
            "Only this project's assigned Head can open the Weekly Report.",
            403,
        )


def get_project_weekly_report(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    cycle: str | None = None,
    *,
    today: date | None = None,
) -> dict:
    """Weekly Report payload for the preview AND the Excel export.

    Both endpoints call exactly this, so the workbook can never contain a
    different row set from the screen it was downloaded from. Authorization is
    re-run here rather than trusted from the caller, which is what makes the
    export endpoint safe against a hand-typed URL.
    """
    from app.modules.projects import weekly_report

    project = _fetch(db, project_id)
    _assert_can_read_weekly_report(db, actor, project)
    return weekly_report.get_project_weekly_report(db, project, cycle, today=today)


def _assert_scope_covers_recorded_progress(
    db: Session, project: Project, new_estimated_tag_count: int
) -> None:
    """Reduction guard — deliberately a no-op in this phase.

    Reducing the estimate is allowed for now (with a reason, and fully preserved
    in history) because the scoped activity-progress service does not exist yet:
    there is no MAX(activity progress) to compare against, and inventing one here
    would duplicate logic the progress phase owns.

    This seam exists so that phase can add the rule — "a new scope may not fall
    below the progress already recorded against it" — by filling in this one
    function, without reworking the revision flow, the endpoint or the UI.
    """
    return


def record_tag_scope_revision(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    *,
    new_estimated_tag_count: int,
    new_status: str,
    reason: str | None,
    expected_revision: int | None = None,
) -> Project:
    """Append one revision and move the project's current scope onto it.

    The single operation that maintains every tag-scope invariant: revision
    numbers dense and unique per project, previous_* copied from the row being
    superseded, a reason always recorded, and the projects.* columns kept in
    step with the newest row. All of it derived server-side — the caller never
    supplies a revision number, a previous value or an author.

    Refuses, in this order:
      403  caller is neither PM nor THIS project's Head
      422  project is not TAG_BASED
      422  count is absent, zero or negative
      422  status is not PROVISIONAL / BASELINED
      409  ``expected_revision`` no longer matches the stored revision
      422  reason is blank while revising an existing scope

    Submitting the values the project already has is not an error and not a
    revision: it returns the project untouched (see the no-op rule below).
    """
    project = _fetch(db, project_id)
    if not authz.can_edit_project(db, actor, project):
        raise AppError(
            "forbidden",
            "Only project managers and this project's Head can set tag scope.",
            403,
        )
    if project.scope_type != SCOPE_TYPE_TAG_BASED:
        raise AppError(
            "validation_error",
            "Tag scope can only be set on a tag-based project.",
            422,
        )
    # Unknown scope is NULL, never 0 — a stored estimate must be a real count.
    if new_estimated_tag_count is None or new_estimated_tag_count <= 0:
        raise AppError(
            "validation_error",
            "Estimated tag count must be greater than 0.",
            422,
        )
    if new_status not in VALID_TAG_SCOPE_STATUSES:
        raise AppError("validation_error", "Unknown tag scope status.", 422)

    # Optimistic concurrency. Two administrators can hold the same form open;
    # whoever saves second must be told their view is stale rather than have
    # their number quietly stack on top of a revision they never saw. Checked
    # before anything is written, and backed by the UNIQUE(project_id, revision)
    # constraint for the case where both commits race past this read.
    if expected_revision is not None and expected_revision != project.tag_scope_revision:
        raise AppError(
            "conflict",
            "The tag scope changed while you were editing it. Refresh and review "
            "the latest values before updating.",
            409,
        )

    # No-op rule: saving the values the project already carries must not mint a
    # revision. History is a record of decisions, and "someone pressed Save"
    # is not one. Idempotent rather than an error, so a double-submit is safe.
    if (
        project.estimated_tag_count == new_estimated_tag_count
        and project.tag_scope_status == new_status
    ):
        return project

    # Reason policy: mandatory when changing an established scope (whitespace is
    # not a reason), defaulted for the very first estimate where "why" is simply
    # that the project is being set up.
    clean_reason = (reason or "").strip()
    if not clean_reason:
        if project.tag_scope_revision > 0:
            raise AppError(
                "validation_error", "A reason is required for a scope change.", 422
            )
        clean_reason = INITIAL_SCOPE_REASON

    _assert_scope_covers_recorded_progress(db, project, new_estimated_tag_count)

    next_revision = project.tag_scope_revision + 1
    db.add(ProjectTagScopeRevision(
        project_id=project.id,
        revision=next_revision,
        previous_estimated_tag_count=project.estimated_tag_count,
        new_estimated_tag_count=new_estimated_tag_count,
        previous_status=project.tag_scope_status,
        new_status=new_status,
        reason=clean_reason,
        changed_by=actor.id,
    ))
    project.estimated_tag_count = new_estimated_tag_count
    project.tag_scope_status = new_status
    project.tag_scope_revision = next_revision
    project.tag_scope_updated_at = datetime.now(timezone.utc)
    project.tag_scope_updated_by = actor.id
    db.add(project)
    # One transaction: the revision row and the projects.* columns commit
    # together or not at all, so current state and history can never diverge.
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError(
            "conflict",
            "The tag scope changed while you were editing it. Refresh and review "
            "the latest values before updating.",
            409,
        )
    db.refresh(project)
    return project


def update_tag_scope(
    db: Session, actor: User, project_id: uuid.UUID, data: TagScopeUpdate
) -> TagScopeOut:
    """PUT /projects/{id}/tag-scope — the managed establish/revise workflow.

    A thin, validated wrapper over the recording primitive: it exists so the
    route never reaches the primitive with unchecked input, and so the response
    is the same shape the tab already reads (current scope + full history),
    letting the client refresh both from one round trip.
    """
    record_tag_scope_revision(
        db,
        actor,
        project_id,
        new_estimated_tag_count=data.estimated_tag_count,
        new_status=data.status,
        reason=data.reason,
        expected_revision=data.expected_revision,
    )
    return get_tag_scope(db, actor, project_id)


def update_project(
    db: Session, actor: User, project_id: uuid.UUID, data: ProjectUpdate
) -> Project:
    project = _fetch(db, project_id)
    # PM (any project) or the employee assigned as THIS project's Head. Checked
    # here rather than with require_role on the route so the rule lives in one
    # place and the router cannot drift from it.
    if not authz.can_edit_project(db, actor, project):
        raise AppError(
            "forbidden",
            "Only project managers and this project's Head can edit it.",
            403,
        )
    fields = data.model_dump(exclude_unset=True)

    if "status" in fields and fields["status"] is not None:
        _validate_status_transition(project.status, fields["status"])

    # scope_type is NOT NULL. An explicit null means "leave it alone" (an older
    # client sending the whole object with the field absent-as-null must not
    # blow up), not "clear the classification".
    if fields.get("scope_type") is None:
        fields.pop("scope_type", None)

    # TAG_BASED -> NONE is allowed with or without existing scope history, and
    # writes nothing but the classification itself: see the deactivation note
    # above the tag-scope section.

    # code is editable (PMs need to fix codes entered before this field
    # existed, or clear it entirely — e.g. reverting a code entered in error —
    # by sending code: null, migration 0078) — but must stay unique among
    # non-deleted projects, same rule create_project enforces. Clearing to
    # None is never a conflict, same reasoning as create_project's own check.
    if "code" in fields and fields["code"] != project.code and fields["code"]:
        if db.execute(
            select(Project).where(
                Project.code == fields["code"],
                Project.deleted_at.is_(None),
                Project.id != project.id,
            )
        ).scalar_one_or_none():
            raise AppError("conflict", "A project with this code already exists.", 409)

    # planned_completion_date via this endpoint is only allowed as an initial set.
    # Once a date exists, changes must go through the dedicated endpoint (which
    # requires a reason and records the change log / timeline event).
    incoming_planned = fields.pop("planned_completion_date", _UNSET)
    if incoming_planned is not _UNSET and project.planned_completion_date is None:
        fields["planned_completion_date"] = incoming_planned

    new_start = fields.get("start_date", project.start_date)
    new_planned = fields.get("planned_completion_date", project.planned_completion_date)
    _validate_dates(new_start, new_planned)

    if "job_code" in fields:
        new_name = fields.get("name") or project.name
        fields["job_code_id"] = _resolve_job_code(
            db, fields.pop("job_code"), new_name, actor.id
        )

    for key, value in fields.items():
        setattr(project, key, value)
    project.updated_by = actor.id
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "A project with this code already exists.", 409)
    db.refresh(project)
    project.member_count = db.execute(  # type: ignore[attr-defined]
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    ).scalar_one()
    _attach_job_codes(db, [project])
    _attach_maintenance_plants(db, [project])
    _attach_heads(db, [project])
    project.days_running = _compute_days_running(project)  # type: ignore[attr-defined]
    return project


def update_planned_completion_date(
    db: Session, actor: User, project_id: uuid.UUID, data: PlannedDateUpdate
) -> Project:
    project = _fetch(db, project_id)
    _validate_dates(project.start_date, data.new_date)

    old_date = project.planned_completion_date
    change = ProjectPlannedDateChange(
        project_id=project_id,
        old_date=old_date,
        new_date=data.new_date,
        changed_by=actor.id,
        reason=data.reason,
    )
    db.add(change)
    project.planned_completion_date = data.new_date
    project.updated_by = actor.id
    db.add(project)
    audit.record_audit(
        db,
        action=AuditAction.PROJECT_PLANNED_DATE_CHANGE,
        actor=actor,
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
        details={
            "old_date": old_date.isoformat() if old_date else None,
            "new_date": data.new_date.isoformat() if data.new_date else None,
            "reason": data.reason,
        },
    )
    _record_timeline(db, project_id, TimelineEventType.PLANNED_DATE_CHANGED, actor, {
        "old_date": old_date.isoformat() if old_date else None,
        "new_date": data.new_date.isoformat() if data.new_date else None,
        "reason": data.reason,
    })
    db.commit()
    db.refresh(project)
    project.member_count = db.execute(  # type: ignore[attr-defined]
        select(func.count()).select_from(ProjectMember).where(
            ProjectMember.project_id == project.id
        )
    ).scalar_one()
    _attach_job_codes(db, [project])
    project.days_running = _compute_days_running(project)  # type: ignore[attr-defined]
    return project


def list_planned_date_changes(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProjectPlannedDateChange]:
    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)
    rows = db.execute(
        select(ProjectPlannedDateChange)
        .where(ProjectPlannedDateChange.project_id == project_id)
        .order_by(ProjectPlannedDateChange.changed_at.desc())
    ).scalars().all()
    # Attach user display names
    user_ids = {r.changed_by for r in rows}
    names: dict[uuid.UUID, str] = {}
    if user_ids:
        from app.modules.users.models import User as UserModel
        user_rows = db.execute(
            select(UserModel).where(UserModel.id.in_(user_ids))
        ).scalars().all()
        for u in user_rows:
            names[u.id] = u.email
    for r in rows:
        r.changed_by_name = names.get(r.changed_by, "")  # type: ignore[attr-defined]
    return list(rows)


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
    audit.record_audit(
        db,
        action=AuditAction.PROJECT_MEMBER_ADD,
        actor=actor,
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
        details={"employee_id": str(employee_id), "role": role.value},
    )
    _record_timeline(db, project_id, TimelineEventType.MEMBER_ADDED, actor, {
        "employee_name": employee.full_name,
        "role": role.value,
    })
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

    prev_role = member.role
    if role == ProjectMemberRole.team_lead:
        _demote_existing_lead(db, project_id, except_id=member.id)
    member.role = role
    db.add(member)
    audit.record_audit(
        db,
        action=AuditAction.PROJECT_MEMBER_ROLE_CHANGE,
        actor=actor,
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
        details={
            "employee_id": str(employee_id),
            "from": prev_role.value,
            "to": role.value,
        },
    )
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
    member_role = member.role
    employee = db.get(Employee, employee_id)
    employee_name = employee.full_name if employee else str(employee_id)
    db.delete(member)
    audit.record_audit(
        db,
        action=AuditAction.PROJECT_MEMBER_REMOVE,
        actor=actor,
        entity_type=EntityType.PROJECT,
        entity_id=project_id,
        details={"employee_id": str(employee_id), "role": member_role.value},
    )
    _record_timeline(db, project_id, TimelineEventType.MEMBER_REMOVED, actor, {
        "employee_name": employee_name,
        "role": member_role.value,
    })
    db.commit()


def list_timeline(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProjectTimelineEvent]:
    project = _fetch(db, project_id)
    _assert_can_view_timeline(db, actor, project)
    return list(
        db.execute(
            select(ProjectTimelineEvent)
            .where(ProjectTimelineEvent.project_id == project_id)
            .order_by(ProjectTimelineEvent.created_at.desc())
        )
        .scalars()
        .all()
    )


def list_led_projects(db: Session, actor: User) -> list[LedProject]:
    """Projects the current user is Head of, each with its active members.

    Returns [] for users who don't Head any live, non-archived project — the
    signal the Work Reports view uses to decide whether to show the Head's
    employee filter. Mirrors the backend report scope, which is now Head-only:
    team leads no longer inherit project-wide report access, so they no longer
    surface here either. It includes every active member of the headed project
    (the Head themselves included).
    """
    me = _current_employee(db, actor)
    if me is None:
        return []
    projects = db.execute(
        select(Project).where(
            Project.head_employee_id == me.id,
            Project.deleted_at.is_(None),
            Project.status != ProjectStatus.archived,
        ).order_by(Project.name)
    ).scalars().all()
    if not projects:
        return []
    result: list[LedProject] = []
    for project in projects:
        rows = db.execute(
            select(Employee)
            .join(ProjectMember, ProjectMember.employee_id == Employee.id)
            .where(
                ProjectMember.project_id == project.id,
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
            ).order_by(Employee.first_name, Employee.last_name)
        ).scalars().all()
        result.append(LedProject(
            project_id=project.id, name=project.name, code=project.code,
            members=[LedProjectMember(employee_id=e.id, name=e.full_name) for e in rows],
        ))
    return result


def list_assignable_employees(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[Employee]:
    """Every active employee that may be staffed onto one of this project's
    activities — the candidate list for the shared assignment form. Restricted
    to staffing managers: the PM, the project Head, or a Lead of any activity in
    the project (Leads staff their own activity's Contributors/QC), so a Head or
    Lead (whose global role is `employee`) can list all candidates instead of
    just their own record."""
    project = _fetch(db, project_id)
    if not (
        authz.can_manage_activity_staffing(db, actor, project)
        or authz.leads_any_activity(db, actor, project_id)
    ):
        raise AppError(
            "forbidden",
            "Only the PM, the project Head, or an activity Lead can view assignable employees.",
            403,
        )
    return list(
        db.execute(
            select(Employee)
            .where(
                Employee.deleted_at.is_(None),
                Employee.status == EmployeeStatus.active,
            )
            .order_by(Employee.first_name, Employee.last_name)
        )
        .scalars()
        .all()
    )


# ---------- activity staffing (Phase 3) ------------------------------------
def list_activity_staffing(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ActivityStaffingOut]:
    """Every activity that currently has staffing on this project, each grouped
    into its Lead, its Contributor list, and the members holding QC. QC is
    additive, so a QC member also appears under lead/contributors. Activities
    with no assignments are omitted. PM / Head / any project member may read
    (same scope as project read)."""
    from app.modules.activity_master.models import ActivityMaster

    project = _fetch(db, project_id)
    _assert_can_read(db, actor, project)

    rows = db.execute(
        select(ProjectActivityMember, Employee, ActivityMaster)
        .join(Employee, Employee.id == ProjectActivityMember.employee_id)
        .join(ActivityMaster, ActivityMaster.id == ProjectActivityMember.activity_id)
        .where(ProjectActivityMember.project_id == project_id)
        .order_by(
            ActivityMaster.sort_order,
            ActivityMaster.name,
            Employee.first_name,
            Employee.last_name,
        )
    ).all()

    groups: dict[uuid.UUID, ActivityStaffingOut] = {}
    order: list[uuid.UUID] = []
    for member, employee, activity in rows:
        member.employee_name = employee.full_name  # type: ignore[attr-defined]
        out = ActivityMemberOut.model_validate(member)
        group = groups.get(activity.id)
        if group is None:
            group = ActivityStaffingOut(
                activity_id=activity.id,
                activity_code=activity.code,
                activity_name=activity.name,
            )
            groups[activity.id] = group
            order.append(activity.id)
        if member.role == ActivityMemberRole.lead:
            group.lead = out
        else:
            group.contributors.append(out)
        if member.is_qc:
            group.qc.append(out)
        group.member_count += 1
    return [groups[aid] for aid in order]


def _assert_no_activity_lead(
    db: Session,
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    except_id: uuid.UUID | None = None,
) -> None:
    """Guard the one-Lead-per-activity rule (also enforced by a partial-unique
    index). ``except_id`` excludes the row being updated in place."""
    stmt = select(ProjectActivityMember.id).where(
        ProjectActivityMember.project_id == project_id,
        ProjectActivityMember.activity_id == activity_id,
        ProjectActivityMember.role == ActivityMemberRole.lead,
    )
    if except_id is not None:
        stmt = stmt.where(ProjectActivityMember.id != except_id)
    if db.execute(stmt.limit(1)).scalar_one_or_none() is not None:
        raise AppError(
            "conflict",
            "This activity already has a Lead. Change the current Lead first.",
            409,
        )


def assign_activity_member(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    data: ActivityMemberCreate,
) -> ActivityMemberOut:
    """Assign an employee to one activity of the project (base role + QC flag).
    PM or the project Head (any activity), or the activity's own Lead (Contributor
    / QC only). Auto-maintains the visibility backbone (adds a project_members
    row) so activity staff can see the project."""
    from app.modules.activity_master.models import ActivityMaster
    from app.modules.activity_master.service import _assert_is_activity

    project = _fetch(db, project_id)
    authority = authz.activity_staffing_authority(db, actor, project, activity_id)
    if authority is None:
        raise AppError(
            "forbidden",
            "Only the PM, the project Head, or this activity's Lead can assign its members.",
            403,
        )
    if authority == "lead" and data.role == ActivityMemberRole.lead:
        raise AppError(
            "forbidden",
            "A Lead can only add Contributors or QC, not another Lead.",
            403,
        )
    if project.status == ProjectStatus.archived:
        raise AppError("validation_error", "Cannot assign to an archived project.", 422)

    # 404 if the activity is missing, 422 if it is a sub-activity node.
    _assert_is_activity(db, activity_id)

    employee = db.get(Employee, data.employee_id)
    if employee is None or employee.deleted_at is not None:
        raise AppError("validation_error", "Employee not found.", 422)
    if employee.status != EmployeeStatus.active:
        raise AppError("validation_error", "Employee is not active.", 422)

    if db.execute(
        select(ProjectActivityMember.id).where(
            ProjectActivityMember.project_id == project_id,
            ProjectActivityMember.activity_id == activity_id,
            ProjectActivityMember.employee_id == data.employee_id,
        )
    ).scalar_one_or_none():
        raise AppError("conflict", "Employee is already assigned to this activity.", 409)

    if data.role == ActivityMemberRole.lead:
        _assert_no_activity_lead(db, project_id, activity_id)

    member = ProjectActivityMember(
        project_id=project_id,
        activity_id=activity_id,
        employee_id=data.employee_id,
        role=data.role,
        is_qc=data.is_qc,
        created_by=actor.id,
    )
    db.add(member)
    _ensure_project_member(db, project_id, data.employee_id, actor)
    activity = db.get(ActivityMaster, activity_id)
    # Timeline: a Lead assignment, a QC assignment, or a plain Contributor add.
    # is_qc on a Lead is subsumed by the Lead event (Lead is the primary role).
    if data.role == ActivityMemberRole.lead:
        _staffing_event = TimelineEventType.ACTIVITY_LEAD_ASSIGNED
    elif data.is_qc:
        _staffing_event = TimelineEventType.ACTIVITY_QC_ASSIGNED
    else:
        _staffing_event = TimelineEventType.ACTIVITY_CONTRIBUTOR_ADDED
    _record_activity_staffing_event(db, project_id, _staffing_event, actor, employee, activity)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "This activity already has a Lead.", 409)
    db.refresh(member)
    member.employee_name = employee.full_name  # type: ignore[attr-defined]
    _notify_assignment(
        db,
        assignee=employee,
        actor=actor,
        project=project,
        role_label=_assignment_role_label(member.role, member.is_qc),
        activity_name=activity.name if activity else None,
    )
    return ActivityMemberOut.model_validate(member)


def update_activity_member(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    employee_id: uuid.UUID,
    data: ActivityMemberUpdate,
) -> ActivityMemberOut:
    """Change an assignment's base role and/or toggle its QC flag. PM or the
    project Head (any activity), or the activity's own Lead (QC on a Contributor
    only — a Lead may not change roles or touch the Lead assignment). Omitted
    fields are left unchanged."""
    from app.modules.activity_master.models import ActivityMaster

    project = _fetch(db, project_id)
    authority = authz.activity_staffing_authority(db, actor, project, activity_id)
    if authority is None:
        raise AppError(
            "forbidden",
            "Only the PM, the project Head, or this activity's Lead can update its members.",
            403,
        )

    member = db.execute(
        select(ProjectActivityMember).where(
            ProjectActivityMember.project_id == project_id,
            ProjectActivityMember.activity_id == activity_id,
            ProjectActivityMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise AppError("not_found", "Activity assignment not found.", 404)

    if authority == "lead":
        # A Lead manages Contributors/QC only: never the Lead row, never a role change.
        if member.role == ActivityMemberRole.lead:
            raise AppError("forbidden", "A Lead cannot modify the activity Lead.", 403)
        if data.role is not None and data.role != member.role:
            raise AppError(
                "forbidden", "A Lead can only add or remove QC on Contributors.", 403
            )

    prev_role, prev_qc = member.role, member.is_qc
    if (
        data.role is not None
        and data.role == ActivityMemberRole.lead
        and member.role != ActivityMemberRole.lead
    ):
        _assert_no_activity_lead(db, project_id, activity_id, except_id=member.id)
    if data.role is not None:
        member.role = data.role
    if data.is_qc is not None:
        member.is_qc = data.is_qc
    db.add(member)

    # Timeline: only for a meaningful change (a QC gain/loss or a promotion to
    # Lead). A no-op update, or a QC toggle that doesn't alter the row, records
    # nothing. Lead is primary, so a QC toggle on a Lead is not surfaced.
    employee = db.get(Employee, employee_id)
    activity = db.get(ActivityMaster, activity_id)
    if employee is not None:
        if prev_role != ActivityMemberRole.lead and member.role == ActivityMemberRole.lead:
            _record_activity_staffing_event(
                db, project_id, TimelineEventType.ACTIVITY_LEAD_ASSIGNED,
                actor, employee, activity,
            )
        elif member.role != ActivityMemberRole.lead and member.is_qc != prev_qc:
            _record_activity_staffing_event(
                db, project_id,
                TimelineEventType.ACTIVITY_QC_ASSIGNED if member.is_qc
                else TimelineEventType.ACTIVITY_QC_REMOVED,
                actor, employee, activity,
            )

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "This activity already has a Lead.", 409)
    db.refresh(member)
    member.employee_name = employee.full_name if employee else ""  # type: ignore[attr-defined]
    # Notify the assignee when the assignment actually changed (role or QC).
    if employee is not None and (member.role != prev_role or member.is_qc != prev_qc):
        _notify_assignment(
            db,
            assignee=employee,
            actor=actor,
            project=project,
            role_label=_assignment_role_label(member.role, member.is_qc),
            activity_name=activity.name if activity else None,
        )
    return ActivityMemberOut.model_validate(member)


def remove_activity_member(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    activity_id: uuid.UUID,
    employee_id: uuid.UUID,
) -> None:
    """Unassign an employee from one activity. PM or the project Head (any
    activity), or the activity's own Lead (Contributors/QC only — a Lead may not
    remove the Lead assignment).

    The employee's project_members visibility row is reference-counted: it is
    dropped once this was their last activity on the project and they aren't the
    Head, so the member count reflects only currently-assigned people."""
    project = _fetch(db, project_id)
    authority = authz.activity_staffing_authority(db, actor, project, activity_id)
    if authority is None:
        raise AppError(
            "forbidden",
            "Only the PM, the project Head, or this activity's Lead can remove its members.",
            403,
        )

    member = db.execute(
        select(ProjectActivityMember).where(
            ProjectActivityMember.project_id == project_id,
            ProjectActivityMember.activity_id == activity_id,
            ProjectActivityMember.employee_id == employee_id,
        )
    ).scalar_one_or_none()
    if member is None:
        raise AppError("not_found", "Activity assignment not found.", 404)
    if authority == "lead" and member.role == ActivityMemberRole.lead:
        raise AppError("forbidden", "A Lead cannot remove the activity Lead.", 403)

    from app.modules.activity_master.models import ActivityMaster

    employee = db.get(Employee, employee_id)
    activity = db.get(ActivityMaster, activity_id)
    db.delete(member)
    # Reference-counted cleanup: once this was their last activity on the project
    # (and they aren't the Head), drop the auto-added visibility row so the
    # member count reflects only currently-assigned people.
    _prune_project_member(db, project, employee_id)
    if employee is not None:
        _record_activity_staffing_event(
            db, project_id, TimelineEventType.ACTIVITY_MEMBER_REMOVED,
            actor, employee, activity,
        )
    db.commit()
