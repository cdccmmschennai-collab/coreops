"""Project Tag Scope consumption — how many of a project's estimated tags a
tag-counted sub-activity has already had reported against it.

The business model, restated because it drives every query here:

  A project's estimated_tag_count is a universe of tags, not a pool shared
  BETWEEN activities. Each tag-counted sub-activity progresses against the whole
  number independently:

      Project scope = 2500
        FMTL Tag Description    1000 / 2500
        Asset Photo Merging      500 / 2500
        Datasheet Population    1200 / 2500

  Within ONE sub-activity the reported counts DO accumulate across employees and
  across days: if employee A reports 500 tags on FMTL Tag Description, the
  remaining capacity for that sub-activity on that project is 2000, for everyone.
  That is what stops the same 2500 tags being reported twice.

Which sub-activities take part is derived, never configured: a sub-activity
counts toward tag scope exactly when its `relevant_count_field` is 'tags' (the
unit the benchmark already reads its actual value from) and the project is
TAG_BASED with an established estimate. Nothing has to be ticked in Activity
Master — an activity measured in tags on a tag-based project is in scope by
construction, and PROJECT MEETING / TRAINING (no unit at all) never are.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import COUNT_FIELD_TAGS, ActivityMaster
from app.modules.projects.models import Project, SCOPE_TYPE_TAG_BASED


def project_tag_capacity(project: Project | None) -> int | None:
    """The scope every tag-counted sub-activity on this project works against,
    or None when the project has no cap to enforce.

    None means "unlimited", and covers three genuinely different situations that
    all behave identically here: a normal (NONE) project, a tag-based project
    whose estimate has not been established yet, and a missing project. Callers
    treat None as "no ceiling" rather than as zero — an unset scope must never
    silently block every entry.
    """
    if project is None or project.scope_type != SCOPE_TYPE_TAG_BASED:
        return None
    return project.estimated_tag_count


def is_tag_counted(sub_activity: ActivityMaster | None) -> bool:
    """Does this sub-activity's reported quantity land in tags_count?"""
    return (
        sub_activity is not None
        and sub_activity.relevant_count_field == COUNT_FIELD_TAGS
    )


def recorded_tags(
    db: Session,
    project_id: uuid.UUID,
    sub_activity_id: uuid.UUID,
    *,
    exclude_report_id: uuid.UUID | None = None,
) -> int:
    """Tags already reported against (project, sub-activity) by anyone, any day.

    `exclude_report_id` leaves out the report currently being written, so
    re-saving or editing a report counts its new numbers instead of stacking
    them on top of its own previous ones. Without it, editing 500 to 600 would
    read as 1100.

    Every report status is counted. A draft is a real claim on the scope (the
    work is being done now), and the legacy approved/rejected rows still hold
    numbers somebody reported. Counting only submitted rows would let two people
    each draft the last 500 tags and both succeed.
    """
    from app.modules.work_reports.models import DailyWorkReport, WorkReportTask

    stmt = (
        select(func.coalesce(func.sum(WorkReportTask.tags_count), 0))
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .where(
            WorkReportTask.project_id == project_id,
            WorkReportTask.sub_activity_id == sub_activity_id,
        )
    )
    if exclude_report_id is not None:
        stmt = stmt.where(WorkReportTask.report_id != exclude_report_id)
    return int(db.execute(stmt).scalar_one() or 0)


def remaining_tags(
    db: Session,
    project: Project | None,
    sub_activity: ActivityMaster | None,
    *,
    exclude_report_id: uuid.UUID | None = None,
) -> int | None:
    """Tags still available on (project, sub-activity), or None when uncapped.

    Never negative: historical data entered before a scope existed (or before it
    was reduced) can legitimately exceed the current estimate, and the honest
    answer for "how much may I still add" is zero, not a negative number.
    """
    capacity = project_tag_capacity(project)
    if capacity is None or not is_tag_counted(sub_activity):
        return None
    used = recorded_tags(
        db, project.id, sub_activity.id, exclude_report_id=exclude_report_id
    )
    return max(0, capacity - used)


def project_tag_progress(db: Session, project: Project) -> list[dict]:
    """Per-sub-activity progress against this project's tag scope.

    One row per tag-counted sub-activity that has actually been reported on this
    project, each with its own reported/remaining against the SAME capacity —
    the independent-progress model, not a shared pool, so the rows deliberately
    do not sum to the project total.

    Driven off what was reported rather than off the Activity Master catalogue:
    listing every tags-unit sub-activity in the system would bury the handful
    this project actually uses under dozens of empty rows.
    """
    from app.modules.work_reports.models import DailyWorkReport, WorkReportTask

    capacity = project_tag_capacity(project)
    if capacity is None:
        return []

    rows = db.execute(
        select(
            ActivityMaster.id,
            ActivityMaster.name,
            func.coalesce(func.sum(WorkReportTask.tags_count), 0).label("reported"),
        )
        .join(WorkReportTask, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .where(
            WorkReportTask.project_id == project.id,
            ActivityMaster.relevant_count_field == COUNT_FIELD_TAGS,
        )
        .group_by(ActivityMaster.id, ActivityMaster.name)
        .order_by(ActivityMaster.name)
    ).all()

    return [
        {
            "sub_activity_id": r.id,
            "sub_activity_name": r.name,
            "reported_tags": int(r.reported or 0),
            "estimated_tag_count": capacity,
            "remaining_tags": max(0, capacity - int(r.reported or 0)),
        }
        for r in rows
    ]
