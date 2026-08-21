"""Production Status service (Phase 1 - backend foundation).

RBAC (resolved through app.core.authz, never re-implemented here):

  read   project_manager  every project
         Project Head     projects where they are `projects.head_employee_id`
         Activity Lead    projects where they lead at least one activity
         everyone else    403 - the tab is not a general project tab

  write  the caller must have management authority over THE SPECIFIC ACTIVITY,
         resolved by `authz.activity_staffing_authority`:
           "full" -> project_manager, or this project's Head
           "lead" -> the assigned Lead of that one activity
           None   -> 403
         This is the same helper that already gates activity staffing changes,
         so "authorized to manage this activity" has exactly one definition in
         the codebase.

History: `create_production_status` only ever INSERTs. Nothing here updates or
deletes a row, so an INPROGRESS -> CLOSED change appends a second row and both
remain readable. "Latest" is derived (newest `created_at` per project+revision+
activity), never stored.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.activity_master.models import LEVEL_ACTIVITY, ActivityMaster
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee
from app.modules.production_status.models import ProjectProductionStatus
from app.modules.production_status.schemas import (
    ProductionStatusCreate,
    ProductionStatusOut,
)
from app.modules.projects.models import Project, ProjectActivityMember
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


# ---------------------------------------------------------------------------
# Fetch + RBAC
# ---------------------------------------------------------------------------

def _fetch_project(db: Session, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)
    return project


def _assert_can_read(db: Session, actor: User, project: Project) -> None:
    """PM, this project's Head, or the Lead of any activity on this project.

    Deliberately NARROWER than ``authz.can_view_project``: an ordinary
    contributor or QC member can open the project but not its Production
    Status. Widening it later is one clause here.
    """
    if actor.role == UserRole.project_manager:
        return
    if authz.is_project_head(db, actor, project):
        return
    if authz.leads_any_activity(db, actor, project.id):
        return
    raise AppError(
        "forbidden",
        "Only the project manager, this project's Head and its activity leads "
        "can view production status.",
        403,
    )


def _assert_can_record(
    db: Session, actor: User, project: Project, activity_id: uuid.UUID
) -> None:
    """Authority over ONE activity, via the shared staffing-authority helper.

    Checked before the activity itself is validated, so an unauthorized caller
    gets the same 403 whether or not the activity they guessed exists.
    """
    if authz.activity_staffing_authority(db, actor, project, activity_id) is None:
        raise AppError(
            "forbidden",
            "You can only record production status for activities you manage.",
            403,
        )


def _fetch_valid_activity(
    db: Session, project: Project, activity_id: uuid.UUID
) -> ActivityMaster:
    """The activity must exist in Activity Master, be a top-level Activity, and
    be one of THIS project's activities.

    A project's activities are the ones it is staffed for
    (``project_activity_members``) - that join is the only structural
    project<->activity link in the system, and it is the same one the Activity
    Lead relationship is built on. No parallel activity list is invented here.
    """
    activity = db.get(ActivityMaster, activity_id)
    if activity is None:
        raise AppError("not_found", "Activity not found.", 404)
    if activity.level != LEVEL_ACTIVITY:
        raise AppError(
            "validation_error",
            "Production status is recorded against an Activity, not a sub-activity.",
            422,
        )
    staffed = db.execute(
        select(ProjectActivityMember.id)
        .where(
            ProjectActivityMember.project_id == project.id,
            ProjectActivityMember.activity_id == activity_id,
        )
        .limit(1)
    ).scalar_one_or_none()
    if staffed is None:
        raise AppError(
            "validation_error",
            "That activity is not part of this project.",
            422,
        )
    return activity


# ---------------------------------------------------------------------------
# Read-model decoration - the API returns names, not ids to resolve
# ---------------------------------------------------------------------------

def _author_names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Real full names for the update authors, falling back to the login email
    for a user with no employee profile. Same one-pass join the tag-scope
    history uses. The role the author held is never part of this."""
    if not user_ids:
        return {}
    names: dict[uuid.UUID, str] = {}
    for uid, email, first, last in db.execute(
        select(User.id, User.email, Employee.first_name, Employee.last_name)
        .outerjoin(Employee, (Employee.user_id == User.id) & (Employee.deleted_at.is_(None)))
        .where(User.id.in_(user_ids))
    ).all():
        names[uid] = f"{first} {last}".strip() if first else email
    return names


def _to_out(
    db: Session, project: Project, rows: list[ProjectProductionStatus]
) -> list[ProductionStatusOut]:
    if not rows:
        return []

    # Plant labels come off the project through the project module's own
    # helper, so Production Status can never show a different plant from the
    # project page.
    from app.modules.projects.service import _attach_maintenance_plants

    _attach_maintenance_plants(db, [project])

    activity_ids = {r.activity_id for r in rows}
    activities = {
        a.id: a
        for a in db.execute(
            select(ActivityMaster).where(ActivityMaster.id.in_(activity_ids))
        ).scalars().all()
    }
    names = _author_names(db, {r.created_by for r in rows})

    out: list[ProductionStatusOut] = []
    for r in rows:
        activity = activities.get(r.activity_id)
        out.append(
            ProductionStatusOut(
                id=r.id,
                project_id=project.id,
                project_code=project.code,
                project_name=project.name,
                planning_plant_code=project.planning_plant_code,  # type: ignore[attr-defined]
                planning_plant_description=project.planning_plant_description,  # type: ignore[attr-defined]
                maintenance_plant_code=project.maintenance_plant_code,  # type: ignore[attr-defined]
                maintenance_plant_description=project.maintenance_plant_description,  # type: ignore[attr-defined]
                revision=r.revision,
                activity_id=r.activity_id,
                activity_name=activity.name if activity else None,
                activity_code=activity.code if activity else None,
                status=r.status,
                tag_count=r.tag_count,
                doc_count=r.doc_count,
                spares_count=r.spares_count,
                crs_count=r.crs_count,
                completed_on=r.completed_on,
                remarks=r.remarks,
                created_by=r.created_by,
                created_by_name=names.get(r.created_by, ""),
                created_at=r.created_at,
            )
        )
    return out


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_latest(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProductionStatusOut]:
    """The CURRENT production status of every (revision, activity) on the
    project - one row each, derived from history rather than stored.

    DISTINCT ON (revision, activity_id) ORDER BY ..., created_at DESC picks the
    newest update per combination. Postgres-specific, like the rest of this
    codebase (CITEXT, JSONB, gen_random_uuid).
    """
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)

    rows = (
        db.execute(
            select(ProjectProductionStatus)
            .where(ProjectProductionStatus.project_id == project_id)
            .distinct(
                ProjectProductionStatus.revision,
                ProjectProductionStatus.activity_id,
            )
            .order_by(
                ProjectProductionStatus.revision,
                ProjectProductionStatus.activity_id,
                ProjectProductionStatus.created_at.desc(),
                # Tie-break so two updates saved in the same transaction (same
                # now()) still resolve to one deterministic "latest".
                ProjectProductionStatus.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    return _to_out(db, project, list(rows))


def list_history(
    db: Session,
    actor: User,
    project_id: uuid.UUID,
    *,
    activity_id: uuid.UUID | None = None,
    revision: str | None = None,
) -> list[ProductionStatusOut]:
    """Every recorded update for the project, newest first.

    Optionally narrowed to one activity and/or one revision - which is what the
    "history for a project/activity" view reads. Nothing is ever filtered out
    by status: a superseded INPROGRESS row stays in the result forever.
    """
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)

    stmt = select(ProjectProductionStatus).where(
        ProjectProductionStatus.project_id == project_id
    )
    if activity_id is not None:
        stmt = stmt.where(ProjectProductionStatus.activity_id == activity_id)
    if revision is not None:
        clean = revision.strip()
        if clean:
            stmt = stmt.where(ProjectProductionStatus.revision == clean)

    rows = (
        db.execute(
            stmt.order_by(
                ProjectProductionStatus.created_at.desc(),
                ProjectProductionStatus.id.desc(),
            )
        )
        .scalars()
        .all()
    )
    return _to_out(db, project, list(rows))


# ---------------------------------------------------------------------------
# Write - append only
# ---------------------------------------------------------------------------

def create_production_status(
    db: Session, actor: User, project_id: uuid.UUID, data: ProductionStatusCreate
) -> ProductionStatusOut:
    """Append ONE status update. Never touches an earlier row.

    Refuses, in this order:
      404  project does not exist (or is archived)
      403  caller does not manage this activity on this project
      404  activity does not exist in Activity Master
      422  activity is a sub-activity, or is not one of this project's
      422  revision is blank
    """
    project = _fetch_project(db, project_id)
    _assert_can_record(db, actor, project, data.activity_id)
    _fetch_valid_activity(db, project, data.activity_id)

    revision = data.revision.strip()
    if not revision:
        raise AppError("validation_error", "Revision is required.", 422)

    remarks = (data.remarks or "").strip() or None

    row = ProjectProductionStatus(
        project_id=project.id,
        revision=revision,
        activity_id=data.activity_id,
        status=data.status,
        tag_count=data.tag_count,
        doc_count=data.doc_count,
        spares_count=data.spares_count,
        crs_count=data.crs_count,
        completed_on=data.completed_on,
        remarks=remarks,
        # The person, resolved from the token - not a role, and not client input.
        created_by=actor.id,
    )
    db.add(row)
    audit.record_audit(
        db,
        action=AuditAction.PRODUCTION_STATUS_RECORD,
        actor=actor,
        entity_type=EntityType.PRODUCTION_STATUS,
        entity_id=project.id,
        details={
            "project_id": str(project.id),
            "revision": revision,
            "activity_id": str(data.activity_id),
            "status": data.status,
            "tag_count": data.tag_count,
            "doc_count": data.doc_count,
            "spares_count": data.spares_count,
            "crs_count": data.crs_count,
        },
    )
    db.commit()
    db.refresh(row)
    return _to_out(db, project, [row])[0]
