"""Production Status service (Phase 1 - backend foundation).

RBAC (resolved through app.core.authz, never re-implemented here):

  read   project_manager  every project
         Project Head     projects where they are `projects.head_employee_id`
         Activity Lead    projects where they lead at least one activity
         everyone else    403 - the tab is not a general project tab

  write  Project Head     every activity on their project, and the only role
                          that may TYPE an activity not in Activity Master
         Activity Lead    the one activity they lead
         project_manager  403 - the PM is READ-ONLY here, deliberately
         everyone else    403
         Resolved by `_record_authority`, which is this module's own rule and
         NOT `authz.activity_staffing_authority` - that helper answers "may you
         change who works on this activity" and hands a PM "full". Production
         status is a claim about work that was done, made by the people who did
         it; the PM reads it and reads the cumulative report nobody else can.

  report the PM cumulative report (`cumulative_report`) is project_manager
         ONLY - see `_assert_can_read_report`. A Head or an activity Lead has
         project-scoped read authority above, which is deliberately not the
         same thing as reading every project at once.

History: `create_production_status` only ever INSERTs. Nothing here UPDATES a
row, so an INPROGRESS -> CLOSED change appends a second row and both remain
readable. "Latest" is derived (newest `created_at` per project+revision+
activity), never stored - and it is derived in exactly ONE place, `_latest_stmt`,
which both the per-project tab and the cumulative PM report read.

The one deletion path is `delete_production_status`: the AUTHOR of a record may
withdraw a record they entered by mistake, and nobody else may - not a Head, not
another Lead, not the PM. That is a correction of a data-entry error, not an
edit of history; every other correction is still a new record.
"""
import re
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.core import authz
from app.modules.activity_master.models import LEVEL_ACTIVITY, ActivityMaster
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.employees.models import Employee
from app.modules.plants.models import MaintenancePlant
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
from app.modules.projects.models import Project
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


# The two kinds of write authority on this tab. Deliberately NOT
# `authz.activity_staffing_authority`, which is about STAFFING and hands a PM
# "full" on every project - see `_record_authority`.
RECORD_AUTHORITY_HEAD = "head"
RECORD_AUTHORITY_LEAD = "lead"


def _record_authority(
    db: Session, actor: User, project: Project, activity_id: uuid.UUID | None
) -> str | None:
    """Who may APPEND a production status update, and for what.

      "head"  this project's assigned Head. Every activity on the project, and
              the only role that may type an activity that is not in Activity
              Master.
      "lead"  the assigned Lead of ONE Activity Master activity, for that
              activity alone.
      None    everyone else - including the project_manager.

    The PM is read-only here BY DESIGN, and this is the one place that says so.
    It is why this function exists at all instead of reusing
    `authz.activity_staffing_authority`, which returns "full" for a PM: that
    helper answers "may you change who works on this activity", which a PM
    certainly may. Production status is a claim about work that was actually
    done, and it is made by the people who did it - the Head who owns the
    project and the Lead who owns the activity. The PM reads it, and reads the
    cumulative report nobody else can (`_assert_can_read_report`).

    A Lead cannot reach "head" by leaving `activity_id` empty: a typed activity
    has no Lead to be, so the label path requires "head" (see
    `_assert_can_record`).
    """
    if authz.is_project_head(db, actor, project):
        return RECORD_AUTHORITY_HEAD
    if activity_id is not None and authz.is_activity_lead(
        db, actor, project.id, activity_id
    ):
        return RECORD_AUTHORITY_LEAD
    return None


def _assert_can_record(
    db: Session, actor: User, project: Project, data: ProductionStatusCreate
) -> str:
    """403 unless the caller may record THIS update. Returns their authority.

    Checked before the activity itself is validated, so an unauthorized caller
    gets the same 403 whether or not the activity they guessed exists.
    """
    authority = _record_authority(db, actor, project, data.activity_id)
    if authority is None:
        raise AppError(
            "forbidden",
            "Only this project's Head and its activity leads can record "
            "production status.",
            403,
        )
    # Typing an activity is the Head's call. A Lead's authority is over one
    # named Activity Master activity, so there is nothing for it to attach to.
    if data.activity_id is None and authority != RECORD_AUTHORITY_HEAD:
        raise AppError(
            "forbidden",
            "Only this project's Head can record production status for an "
            "activity that is not in Activity Master.",
            403,
        )
    return authority


def _validate_maintenance_plant(
    db: Session, project: Project, maintenance_plant_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Accept a Maintenance Plant only if this project could have offered it.

    "Could have offered it" has exactly one definition, and it is the one the
    Project Edit page's dropdown already uses:
    `plants.service.list_maintenance_plants(planning_plant_code=...)` - the
    plants belonging to the project's Planning Plant, active ones only. This
    function calls THAT function rather than re-deriving the relationship, so
    the dropdown and this check can never disagree and no second plant lookup
    exists in the codebase.

    Returns the id to store, or None:
      None in     -> None out. Choosing no plant is legitimate: a project whose
                     Planning Plant has no Maintenance Plants has none to offer,
                     and the form must not be blocked by that.
      valid in    -> that id.
      anything else -> 422. An unrelated or inactive plant is rejected rather
                     than silently dropped, so a mis-wired client fails loudly.

    The plant is NEVER inferred from the Planning Plant. A project with no
    Planning Plant can offer no Maintenance Plant at all, so any selection
    against it is refused.
    """
    if maintenance_plant_id is None:
        return None

    from app.modules.plants.service import list_maintenance_plants

    # The project's Planning Plant, resolved through the projects module's own
    # helper so the direct-link/legacy-parent precedence is not restated here.
    _attach_plants(db, [project])
    planning_code = project.planning_plant_code  # type: ignore[attr-defined]
    if not planning_code:
        raise AppError(
            "validation_error",
            "This project has no Planning Plant, so no maintenance plant can be "
            "selected for it.",
            422,
        )

    allowed = {
        row["id"]
        for row in list_maintenance_plants(
            db, active_only=True, planning_plant_code=planning_code
        )
    }
    if maintenance_plant_id not in allowed:
        raise AppError(
            "validation_error",
            "That maintenance plant does not belong to this project.",
            422,
        )
    return maintenance_plant_id


def _fetch_valid_activity(db: Session, activity_id: uuid.UUID) -> ActivityMaster:
    """The activity must exist in Activity Master and be a top-level Activity.

    Deliberately NOT narrowed to the project's activity staffing any more. A
    project is staffed for the activities people are assigned to work on, which
    is a different question from what a Head reports production against: the
    Head owns the whole project's output and needs every activity available,
    including ones nobody is formally staffed for yet. Requiring staffing meant
    a project with none had nothing to record at all, which is the state this
    change exists to fix.

    Authority is still per-activity and unchanged in strength - a Lead reaches
    only the activity they lead (`_record_authority`). This function answers
    "is this a real Activity", not "may you use it".

    A sub-activity is still refused: production status is recorded against an
    Activity, and that has not changed.
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
    """Bulk-resolve the Activity Master rows these records point at.

    Rows with a typed activity have no `activity_id` and are simply not part of
    the lookup - their name is already on the row.
    """
    ids = {r.activity_id for r in rows if r.activity_id}
    if not ids:
        return {}
    return {
        a.id: a
        for a in db.execute(
            select(ActivityMaster).where(ActivityMaster.id.in_(ids))
        ).scalars().all()
    }


def _record_plants_by_id(
    db: Session, rows: list[ProjectProductionStatus]
) -> dict[uuid.UUID, MaintenancePlant]:
    """The Maintenance Plants THESE ROWS point at (migration 0071).

    Keyed off `maintenance_plant_id` on each record - deliberately not off the
    project, which carries its own unrelated plant fields. One bulk query for
    the whole result set, never one per row.

    An inactive plant is still resolved: a record recorded against a plant that
    was later retired must keep showing the plant it was recorded against. Only
    the *choosing* of a plant is restricted to active ones.
    """
    ids = {r.maintenance_plant_id for r in rows if r.maintenance_plant_id}
    if not ids:
        return {}
    return {
        mp.id: mp
        for mp in db.execute(
            select(MaintenancePlant).where(MaintenancePlant.id.in_(ids))
        ).scalars().all()
    }


def _activity_display(
    activity: ActivityMaster | None, activity_label: str | None
) -> str:
    """The ACTIVITY cell, however the activity was named.

    An Activity Master activity reads as its name (falling back to its code); a
    typed activity reads as exactly what was typed. ONE function, used by the
    project tab, the report and the workbook alike, so no screen has to know -
    or show - which kind of row it is looking at.
    """
    if activity is not None:
        return (activity.name or "").strip() or (activity.code or "").strip()
    return (activity_label or "").strip()


def _to_out(
    db: Session, project: Project, rows: list[ProjectProductionStatus]
) -> list[ProductionStatusOut]:
    if not rows:
        return []

    _attach_plants(db, [project])

    activities = _activities_by_id(db, rows)
    names = _author_names(db, {r.created_by for r in rows})
    plants = _record_plants_by_id(db, rows)

    out: list[ProductionStatusOut] = []
    for r in rows:
        activity = activities.get(r.activity_id) if r.activity_id else None
        # THIS RECORD's plant, from its own maintenance_plant_id - never the
        # project's plant fields and never derived from the Planning Plant.
        # Null stays null.
        plant = plants.get(r.maintenance_plant_id) if r.maintenance_plant_id else None
        out.append(
            ProductionStatusOut(
                id=r.id,
                project_id=project.id,
                project_code=project.code,
                project_name=project.name,
                planning_plant_code=project.planning_plant_code,  # type: ignore[attr-defined]
                planning_plant_description=project.planning_plant_description,  # type: ignore[attr-defined]
                maintenance_plant_id=r.maintenance_plant_id,
                maintenance_plant_code=plant.code if plant else None,
                maintenance_plant_description=plant.description if plant else None,
                revision=r.revision,
                activity_id=r.activity_id,
                # One resolved name whichever way the activity was named, so a
                # client renders `activity_name` and never combines fields.
                activity_name=_activity_display(activity, r.activity_label) or None,
                activity_code=activity.code if activity else None,
                activity_label=r.activity_label,
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
    # The typed activity is part of the identity exactly as an id is (migration
    # 0072): two updates typed "HIERARCHY QA/QC" on the same project and
    # revision are the same combination and the newer supersedes the older.
    # Postgres treats NULLs as equal in DISTINCT ON, so an id-named row groups
    # by its id with a NULL label, and a typed row groups by its label with a
    # NULL id - without either colliding with the other.
    ProjectProductionStatus.activity_label,
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
    activity_label: str | None = None,
    revision: str | None = None,
) -> list[ProductionStatusOut]:
    """Every recorded update for the project, newest first.

    Optionally narrowed to one activity and/or one revision - which is what the
    "history for a project/activity" view reads. Nothing is ever filtered out
    by status: a superseded INPROGRESS row stays in the result forever.

    An activity is named the same two ways it is on the record itself:
    `activity_id` for an Activity Master activity, `activity_label` for one that
    was typed. A caller sends whichever the row it is opening the trail for
    carries, so a typed activity has its own history exactly as a master one
    does.
    """
    project = _fetch_project(db, project_id)
    _assert_can_read(db, actor, project)

    stmt = select(ProjectProductionStatus).where(
        ProjectProductionStatus.project_id == project_id
    )
    if activity_id is not None:
        stmt = stmt.where(ProjectProductionStatus.activity_id == activity_id)
    if activity_label is not None:
        clean_label = activity_label.strip()
        if clean_label:
            stmt = stmt.where(
                ProjectProductionStatus.activity_label == clean_label
            )
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
      403  caller is not this project's Head, nor the Lead of this activity
           (a project_manager is READ-ONLY here - see `_record_authority`)
      403  a Lead tried to type an activity of their own
      404  activity does not exist in Activity Master
      422  activity is a sub-activity
      422  maintenance plant does not belong to this project
      422  revision is blank
    """
    project = _fetch_project(db, project_id)
    _assert_can_record(db, actor, project, data)
    if data.activity_id is not None:
        _fetch_valid_activity(db, data.activity_id)
    # Optional. None stays None - a project with no Maintenance Plants to offer
    # still records production status.
    maintenance_plant_id = _validate_maintenance_plant(
        db, project, data.maintenance_plant_id
    )

    revision = data.revision.strip()
    if not revision:
        raise AppError("validation_error", "Revision is required.", 422)

    remarks = (data.remarks or "").strip() or None

    row = ProjectProductionStatus(
        project_id=project.id,
        revision=revision,
        # Exactly one of these is set - the schema's `_exactly_one_activity`
        # already refused anything else, and the table's CHECK is the backstop.
        activity_id=data.activity_id,
        activity_label=data.activity_label,
        maintenance_plant_id=maintenance_plant_id,
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
            "activity_id": str(data.activity_id) if data.activity_id else None,
            "activity_label": data.activity_label,
            "maintenance_plant_id": (
                str(maintenance_plant_id) if maintenance_plant_id else None
            ),
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


def delete_production_status(
    db: Session, actor: User, project_id: uuid.UUID, record_id: uuid.UUID
) -> None:
    """Delete ONE record - only the person who entered it may do so.

    The single exception to this module's append-only rule, and a narrow one: a
    record entered by mistake belongs to whoever entered it, and only they can
    withdraw it. There is deliberately no wider power here - a Head cannot
    delete a Lead's record, a Lead cannot delete another Lead's, and the
    project_manager (read-only on this tab by design - see `_record_authority`)
    cannot delete anyone's. Nothing else in the module changed: correcting a
    figure is still a new record that supersedes the old one.

    Ownership is `created_by`, the users.id stamped from the token when the
    record was saved. There is no second ownership field and no client-supplied
    identity - the same fact `created_by_name` is rendered from.

    Refuses, in this order:
      404  project does not exist (or is archived)
      403  caller may not even read this project's production status
      404  record does not exist, or belongs to another project
      403  the caller did not create it

    Deleting the current row simply uncovers the one before it: "latest" is
    derived per project+revision+activity (`_latest_stmt`), so the previous
    update in that trail becomes current again with nothing to recompute. If it
    was the only row, the combination leaves the table entirely.
    """
    project = _fetch_project(db, project_id)
    # The read gate first, so someone with no business on this project gets the
    # same 403 whether or not the id they guessed exists.
    _assert_can_read(db, actor, project)

    row = db.get(ProjectProductionStatus, record_id)
    if row is None or row.project_id != project.id:
        raise AppError("not_found", "Production status record not found.", 404)

    # THE control. The Delete button is hidden from everyone else purely for
    # convenience; this is what actually stops a direct API call.
    if row.created_by != actor.id:
        raise AppError(
            "forbidden",
            "You can only delete a production status record you recorded "
            "yourself.",
            403,
        )

    audit.record_audit(
        db,
        action=AuditAction.PRODUCTION_STATUS_DELETE,
        actor=actor,
        entity_type=EntityType.PRODUCTION_STATUS,
        entity_id=project.id,
        details={
            "project_id": str(project.id),
            "record_id": str(row.id),
            "revision": row.revision,
            "activity_id": str(row.activity_id) if row.activity_id else None,
            "activity_label": row.activity_label,
            "status": row.status,
            "tag_count": row.tag_count,
            "doc_count": row.doc_count,
            "spares_count": row.spares_count,
            "crs_count": row.crs_count,
            "completed_on": row.completed_on.isoformat() if row.completed_on else None,
        },
    )
    db.delete(row)
    db.commit()


# ---------------------------------------------------------------------------
# PM cumulative report (Phase 4) - read only, one dataset for preview + Excel
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# The report's month filter (Phase 5)
# ---------------------------------------------------------------------------
#
# The month is taken from the record's `created_at` - WHEN THE UPDATE WAS
# RECORDED - and never from `completed_on`. An IN PROGRESS update legitimately
# has no completion date, so filtering on `completed_on` would silently drop
# exactly the rows a PM opens a month to look at.
#
# UTC, on both sides of the feature: the bucket a record falls into
# (`_month_expr`) and the window a filter selects (`_month_bounds`) are computed
# the same way, so a month offered by the dropdown can never come back empty
# because the two disagreed. It also matches what the UI already shows - every
# timestamp in this module is rendered from the leading digits of the serialized
# ISO string, which are UTC.

# "2026-08". A plain, sortable key: lexicographic order IS chronological order,
# which is what lets the dropdown be ordered by the same expression it groups by.
MONTH_FORMAT = "YYYY-MM"


def _month_expr():
    """The month bucket a production status record belongs to, as SQL."""
    return func.to_char(
        func.timezone("UTC", ProjectProductionStatus.created_at), MONTH_FORMAT
    )


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """`"2026-08"` -> the half-open window `[2026-08-01Z, 2026-09-01Z)`.

    Half-open on purpose: `>= start` and `< end` needs no "last day of the
    month" arithmetic and cannot drop a record recorded in the final second of
    the month.
    """
    # Matched strictly rather than parsed leniently: "26-08" is a real date to
    # `int()` (the year 26) and would silently return an empty report the client
    # would then present as a filtered one.
    matched = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", (month or "").strip())
    if matched is None:
        raise AppError(
            "validation_error",
            "Month must be written as YYYY-MM, for example 2026-08.",
            422,
        )
    year, mon = int(matched.group(1)), int(matched.group(2))
    start = datetime(year, mon, 1, tzinfo=timezone.utc)
    end = (
        datetime(year + 1, 1, 1, tzinfo=timezone.utc)
        if mon == 12
        else datetime(year, mon + 1, 1, tzinfo=timezone.utc)
    )
    return start, end


def _available_months(db: Session) -> list[str]:
    """Every month that actually has production status records, ascending.

    Derived from ALL records, not from the latest-per-combination set the report
    renders: a combination whose newest update is in September may still have an
    August update, and August must stay selectable so that row can be read.

    Deliberately independent of whichever month is currently selected - the
    dropdown must never collapse to the one option the PM already picked.

    Archived (soft-deleted) projects are excluded, matching the report itself, so
    the dropdown cannot offer a month whose only records the report will not
    show.
    """
    month = _month_expr()
    return [
        m
        for m in db.execute(
            select(month)
            .join(Project, Project.id == ProjectProductionStatus.project_id)
            .where(Project.deleted_at.is_(None))
            .distinct()
            .order_by(month)
        )
        .scalars()
        .all()
        if m
    ]


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


def _project_plant_display(
    project: Project, plant_code: str | None, revision: str | None
) -> str:
    """The report's PROJECT / PLANT cell.

        "4460-GC22104900 - KAHM REV-0"

    Three parts, joined only when they are actually there:

        <project> - <maintenance plant> <revision>

    project          the project's code ("4460-GC22104900",
                     "NGLC2-GC10108000-PUMPING STATION") - the identifier the
                     Projects UI names a project by. Falls back to the project's
                     descriptive name only if a project somehow has no code.
        - plant      THIS RECORD's Maintenance Plant code, from its own
                     `maintenance_plant_id`. NEVER the Planning Plant, and never
                     the project's own plant column.
        revision     appended so REV-0 and REV-1 of one activity stay visibly
                     distinct now that the workbook has no REVISION column of
                     its own.

    Any absent part is omitted along with its separator, so the cell is always
    clean - a missing plant produces "4391-GC21107300 REV-0", never
    "4391-GC21107300 - REV-0", "... / null", "... / -" or "... / undefined".

    Note on the spec's "no maintenance plant -> project alone": that holds when
    there is also no revision. `revision` is NOT NULL on the table, so dropping
    it whenever a plant is missing would erase the only thing distinguishing two
    rows of the same project and activity - which section 9's revision-isolation
    rule forbids. The revision is therefore kept and the plant segment alone is
    dropped.

    Resolved HERE rather than in the browser precisely because the Excel is
    rendered server-side: if each side built this string itself, the file and
    the preview would be two implementations of one column, free to drift.
    """
    text = (project.code or "").strip() or (project.name or "").strip()
    plant = (plant_code or "").strip()
    rev = (revision or "").strip()
    if plant:
        text = f"{text} - {plant}" if text else plant
    if rev:
        text = f"{text} {rev}" if text else rev
    return text






def cumulative_report(db: Session, actor: User, month: str | None = None) -> dict:
    """The PM's cumulative Production Status - the latest row for every
    project + revision + activity in the system, in one query.

    THE dataset. The JSON endpoint serialises this and the .xlsx endpoint
    renders this same dict into a workbook, so the file always holds exactly the
    rows the PM reviewed on screen - there is no second query, no second
    ordering and no second "latest". `month` is passed straight through by both
    endpoints for the same reason: the filter is part of the dataset's
    definition, so the download cannot hold a different set of rows from the
    preview it was taken from.

    `month` ("2026-08", or None for every month):

      None    the report is exactly what it has always been - every project,
              every revision, every activity, cumulative.

      set     narrowed to the records RECORDED in that month (`created_at`, see
              the module note above - never `completed_on`, which an IN PROGRESS
              record does not have). The narrowing happens BEFORE the DISTINCT
              ON, so each combination resolves to its latest update *within that
              month*: asking for August shows what August's records said, not
              what a later September update replaced them with.

      A month with no records is a valid, empty report - not an error.

    `months` on the result lists every month that has records at all, so the
    caller can offer the choice without a second endpoint, and the list does not
    shrink to whatever month is currently selected.

    Nothing else filters. There is no project, activity or status filter here by
    design: the report is all-project and cumulative, and the month is the only
    narrowing it accepts.

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
    selected = (month or "").strip() or None
    stmt = _latest_stmt()
    if selected is not None:
        # Narrowed HERE, on the inner statement, so the DISTINCT ON runs over
        # the month's records and each combination resolves to its latest update
        # within the month. Filtering the outer query instead would first pick
        # each combination's newest row overall and then throw away any that
        # happened to fall outside the month - so a row updated again later
        # would vanish from the earlier month entirely.
        #
        # Still one database query: the filter is a WHERE, not a second pass in
        # Python over every historical record.
        start, end = _month_bounds(selected)
        stmt = stmt.where(
            ProjectProductionStatus.created_at >= start,
            ProjectProductionStatus.created_at < end,
        )
    latest = aliased(ProjectProductionStatus, stmt.subquery())
    activity = aliased(ActivityMaster)
    # Each ROW's own Maintenance Plant (migration 0071), joined in the same
    # query. An outer join because choosing a plant is optional - a row without
    # one still belongs in the report.
    plant = aliased(MaintenancePlant)

    rows = list(
        db.execute(
            select(latest, Project, activity, plant)
            .join(Project, Project.id == latest.project_id)
            .outerjoin(activity, activity.id == latest.activity_id)
            .outerjoin(plant, plant.id == latest.maintenance_plant_id)
            .where(Project.deleted_at.is_(None))
            .order_by(
                Project.code,
                latest.revision,
                # The name the row is actually shown under, so a typed activity
                # sorts among the Activity Master ones instead of bunching at
                # one end on a NULL join. Same expression the ACTIVITY cell is
                # rendered from.
                func.coalesce(activity.name, latest.activity_label),
                latest.activity_id,
                latest.activity_label,
            )
        ).all()
    )

    # Author names in one bulk query for the whole report, the same shape
    # `_to_out` uses - never one lookup per row. The projects no longer need
    # `_attach_plants` here: the report's plant is the RECORD's, joined above,
    # and the project's own plant columns are not part of this cell any more.
    names = _author_names(db, {r.created_by for r, _p, _a, _mp in rows})

    out: list[ProductionStatusReportRow] = []
    for serial, (r, project, activity_row, plant_row) in enumerate(rows, start=1):
        out.append(
            ProductionStatusReportRow(
                serial=serial,
                id=r.id,
                project_id=project.id,
                project_code=project.code,
                # project + THIS RECORD's plant + revision, cleanly combined.
                project_plant=_project_plant_display(
                    project,
                    plant_row.code if plant_row else None,
                    r.revision,
                ),
                maintenance_plant_id=r.maintenance_plant_id,
                maintenance_plant_code=plant_row.code if plant_row else None,
                # Still in the dataset even though the workbook no longer gives
                # it its own column - it identifies the row and its history.
                revision=r.revision,
                activity_id=r.activity_id,
                # One column, both kinds of activity - see _activity_display.
                activity=_activity_display(activity_row, r.activity_label),
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
        # The filter this dataset was built with - echoed back so a client can
        # tell which report it is holding. None means the cumulative all-months
        # report.
        "month": selected,
        # Every month that has records, whatever the current filter is.
        "months": _available_months(db),
        # The FILTERED count. `rows` and `row_count` always describe the same
        # list, so "12 rows" on screen is 12 rows in the file.
        "row_count": len(out),
        "rows": out,
    }


def report_filename(today: date | None = None, month: str | None = None) -> str:
    """`PRODUCTION STATUS [21 AUG 2026].xlsx`, or `[AUG 2026]` for one month.

    Same shape as the weekly report's filename (uppercase name, bracketed date),
    so CoreOps exports land in a downloads folder looking like one family.
    Characters that would break a Content-Disposition header are stripped.

    A month-filtered download is named for the MONTH rather than for today, so
    two files downloaded on the same day are told apart by what is in them. The
    unfiltered name is unchanged.
    """
    selected = (month or "").strip() or None
    if selected is not None:
        start, _end = _month_bounds(selected)
        name = f"PRODUCTION STATUS [{start.strftime('%b').upper()} {start.year}].xlsx"
    else:
        day = today or datetime.now(timezone.utc).date()
        name = (
            f"PRODUCTION STATUS [{day.day} {day.strftime('%b').upper()} {day.year}].xlsx"
        )
    return "".join(c for c in name if c.isprintable() and c not in '"\\/:*?<>|')
