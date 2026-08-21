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

  report the PM cumulative report (`cumulative_report`) is project_manager
         ONLY - see `_assert_can_read_report`. A Head or an activity Lead has
         project-scoped read authority above, which is deliberately not the
         same thing as reading every project at once.

History: `create_production_status` only ever INSERTs. Nothing here updates or
deletes a row, so an INPROGRESS -> CLOSED change appends a second row and both
remain readable. "Latest" is derived (newest `created_at` per project+revision+
activity), never stored - and it is derived in exactly ONE place, `_latest_stmt`,
which both the per-project tab and the cumulative PM report read.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.core import authz
from app.modules.activity_master.models import LEVEL_ACTIVITY, ActivityMaster
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee
from app.modules.production_status.models import (
    PRODUCTION_STATUS_CLOSED,
    PRODUCTION_STATUS_IN_PROGRESS,
    ProjectProductionStatus,
)
from app.modules.production_status.schemas import (
    ProductionStatusCreate,
    ProductionStatusOut,
    ProductionStatusReportRow,
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


def _assert_can_read_report(actor: User) -> None:
    """The cumulative, all-projects report is project_manager ONLY.

    Deliberately NOT `_assert_can_read` without a project. That rule is
    per-project and answers "may you open THIS project's tab"; a Head or an
    activity Lead passes it for their own projects and must still not receive a
    report spanning every project in the company. Widening this is one clause
    here, and it is the only clause - the frontend hiding the button is
    convenience, never the control.

    Takes no `db` and no project: the answer depends on the caller's role alone,
    so there is nothing to look up.
    """
    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden",
            "Only the project manager can view the cumulative production "
            "status report.",
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


def _attach_plants(db: Session, projects: list[Project]) -> None:
    """Plant labels come off the project through the project module's own
    helper, so Production Status can never show a different plant from the
    project page. Bulk by design - the cumulative report passes every project
    at once and must not issue one query per project."""
    from app.modules.projects.service import _attach_maintenance_plants

    _attach_maintenance_plants(db, projects)


def _activities_by_id(
    db: Session, rows: list[ProjectProductionStatus]
) -> dict[uuid.UUID, ActivityMaster]:
    return {
        a.id: a
        for a in db.execute(
            select(ActivityMaster).where(
                ActivityMaster.id.in_({r.activity_id for r in rows})
            )
        ).scalars().all()
    }


def _to_out(
    db: Session, project: Project, rows: list[ProjectProductionStatus]
) -> list[ProductionStatusOut]:
    if not rows:
        return []

    _attach_plants(db, [project])

    activities = _activities_by_id(db, rows)
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
# "Latest" - ONE definition, read by the project tab and the PM report alike
# ---------------------------------------------------------------------------

# The combination a production status is current FOR. project_id leads, so the
# same statement answers both "latest on this project" (with a project filter
# bolted on) and "latest everywhere" (with none) - there is no second, subtly
# different spelling of "latest" anywhere in the codebase.
_LATEST_KEY = (
    ProjectProductionStatus.project_id,
    ProjectProductionStatus.revision,
    ProjectProductionStatus.activity_id,
)


def _latest_stmt():
    """DISTINCT ON (project, revision, activity) ORDER BY ..., created_at DESC.

    Picks the newest update per combination IN THE DATABASE - the whole history
    is never loaded into Python to be reduced there. Postgres-specific, like the
    rest of this codebase (CITEXT, JSONB, gen_random_uuid).

    Every superseded row is passed over, not deleted: the append-only trail
    behind each of these rows stays intact and is what the per-project History
    dialog reads.
    """
    return (
        select(ProjectProductionStatus)
        .distinct(*_LATEST_KEY)
        .order_by(
            *_LATEST_KEY,
            ProjectProductionStatus.created_at.desc(),
            # Tie-break so two updates saved in the same transaction (same
            # now()) still resolve to one deterministic "latest".
            ProjectProductionStatus.id.desc(),
        )
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------

def list_latest(
    db: Session, actor: User, project_id: uuid.UUID
) -> list[ProductionStatusOut]:
    """The CURRENT production status of every (revision, activity) on the
    project - one row each, derived from history rather than stored.
    """
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)

    rows = (
        db.execute(
            _latest_stmt().where(ProjectProductionStatus.project_id == project_id)
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


# ---------------------------------------------------------------------------
# PM cumulative report (Phase 4) - read only, one dataset for preview + Excel
# ---------------------------------------------------------------------------

# The stored values become words a reader understands here, and only here on
# this side of the wire. The VALUES are untouched (`in_progress` / `closed`):
# this is a rendering of the existing vocabulary, not a second one. Both the
# browser preview and the workbook print `status_label`, so a row can never read
# "CLOSED" on screen and something else in the file.
PRODUCTION_STATUS_LABELS: dict[str, str] = {
    PRODUCTION_STATUS_IN_PROGRESS: "IN PROGRESS",
    PRODUCTION_STATUS_CLOSED: "CLOSED",
}


def _status_label(status: str) -> str:
    """A status from a newer backend renders as itself rather than blanking the
    cell - an unrecognised status is information, not a reason to show nothing.
    """
    return PRODUCTION_STATUS_LABELS.get(status, status)


def _project_plant(project: Project) -> str:
    """The report's PROJECT / PLANT cell - "GC25100600 / 1102".

    The same convention the Production Status tab's header line already uses
    (frontend production-status.ts::formatProjectPlant): the project code, then
    the Maintenance Plant if the project has one, else its Planning Plant.
    Maintenance wins because it is the more specific location, and a project
    loaded from the project master leaves it null - so the Planning Plant keeps
    the cell populated either way.

    Resolved HERE rather than in the browser precisely because the Excel is
    rendered server-side: if each side built this string itself, the file and
    the preview would be two implementations of one column, free to drift. The
    plant is read off the project through the projects module's own helper, so
    it is never a second project/plant field.
    """
    plant = (
        getattr(project, "maintenance_plant_code", None)
        or getattr(project, "planning_plant_code", None)
    )
    parts = [p for p in (project.code, plant) if p and p.strip()]
    return " / ".join(parts) if parts else (project.name or "").strip()


def _activity_label(activity: ActivityMaster | None) -> str:
    if activity is None:
        return ""
    return (activity.name or "").strip() or (activity.code or "").strip()


def cumulative_report(db: Session, actor: User) -> dict:
    """The PM's cumulative Production Status - the latest row for every
    project + revision + activity in the system, in one query.

    THE dataset. The JSON endpoint serialises this and the .xlsx endpoint
    renders this same dict into a workbook, so the file always holds exactly the
    rows the PM reviewed on screen - there is no second query, no second
    ordering and no second "latest".

    What it is not:

      Not a history export. Superseded updates are passed over by the DISTINCT
      ON, and they stay exactly where they are - the per-project History dialog
      is still the only place the full trail is read.

      Not a roll-up. TAG / DOC / SPARES / CRS are carried through as four
      independent values; nothing here sums, averages or combines them, and
      REV-0 survives alongside REV-1 because a revision is part of the row's
      identity, not a version of it.

    Ordering (identical for both renderers, because there is one list): project
    code, then revision, then activity name, then the activity id so two
    equally-named activities never swap places between calls. `serial` is
    stamped from that order, which is what makes the preview's S.NO and the
    workbook's S.NO the same number for the same row.

    Archived projects: a soft-deleted project (`deleted_at`) is excluded - it is
    gone from every other list in CoreOps. A project with status `archived` is
    NOT excluded: it is still a real project whose recorded production is part
    of the cumulative picture.
    """
    _assert_can_read_report(actor)

    # The shared DISTINCT ON, as a subquery. Two reasons it is not the outer
    # query: DISTINCT ON forces ORDER BY to lead with its own key, and this
    # report is ordered by project CODE, which lives on another table. Wrapping
    # keeps the latest-row selection in the database (never "load all history
    # and pick in Python") while the outer query is free to sort for a reader.
    latest = aliased(ProjectProductionStatus, _latest_stmt().subquery())
    activity = aliased(ActivityMaster)

    rows = list(
        db.execute(
            select(latest, Project, activity)
            .join(Project, Project.id == latest.project_id)
            .outerjoin(activity, activity.id == latest.activity_id)
            .where(Project.deleted_at.is_(None))
            .order_by(
                Project.code,
                latest.revision,
                activity.name,
                latest.activity_id,
            )
        ).all()
    )

    # Plants and author names in two bulk queries for the whole report, the same
    # shape `_to_out` uses - never one lookup per row.
    _attach_plants(db, [project for _r, project, _a in rows])
    names = _author_names(db, {r.created_by for r, _p, _a in rows})

    out: list[ProductionStatusReportRow] = []
    for serial, (r, project, activity_row) in enumerate(rows, start=1):
        out.append(
            ProductionStatusReportRow(
                serial=serial,
                id=r.id,
                project_id=project.id,
                project_code=project.code,
                project_plant=_project_plant(project),
                revision=r.revision,
                activity_id=r.activity_id,
                activity=_activity_label(activity_row),
                status=r.status,
                status_label=_status_label(r.status),
                # Four independent values, straight off the record. A stored 0
                # stays the integer 0 - the workbook needs a real number in the
                # cell so the PM can filter, sort and sum the column.
                tag_count=r.tag_count,
                doc_count=r.doc_count,
                spares_count=r.spares_count,
                crs_count=r.crs_count,
                # Null stays null. No date is ever invented for an update that
                # has not completed; both renderers leave the cell blank.
                completed_on=r.completed_on,
                # Exactly what the author typed, untruncated.
                remarks=r.remarks,
                # The real person, from the same join the tab reads. Never the
                # role they held - see _author_names.
                by=names.get(r.created_by, ""),
            )
        )

    return {
        "generated_at": datetime.now(timezone.utc),
        "row_count": len(out),
        "rows": out,
    }


def report_filename(today: date | None = None) -> str:
    """`PRODUCTION STATUS [21 AUG 2026].xlsx`.

    Same shape as the weekly report's filename (uppercase name, bracketed date),
    so CoreOps exports land in a downloads folder looking like one family.
    Characters that would break a Content-Disposition header are stripped.
    """
    day = today or datetime.now(timezone.utc).date()
    name = f"PRODUCTION STATUS [{day.day} {day.strftime('%b').upper()} {day.year}].xlsx"
    return "".join(c for c in name if c.isprintable() and c not in '"\\/:*?<>|')
