"""Task-continuation work items — lifecycle math + create / continue / complete.

A WorkItem (models.WorkItem) is the authoritative record for a TASK_BASED
(lumpsum) activity that may span several daily reports. This module is the pure
domain layer over it:

  * lifecycle math (derived from dates, never a stored status)
  * resolving a work-report task row to a work item on save (START vs CONTINUE)
  * completion transitions (one-way after submit; correctable while draft)
  * the open-task query behind GET /work-reports/open-tasks

Everything here is gated by settings.TASK_CONTINUATION_ENABLED at the *call
sites* in work_reports/service.py — this module never reads the flag, so it
stays unit-testable and legacy behaviour is decided in one place.

Scope: TASK_BASED only. NUMERIC daily-quantity benchmarks never touch this.
"""
import enum
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.work_reports.models import DailyWorkReport, WorkItem, WorkReportTask
from app.shared.errors import AppError


class WorkItemLifecycle(str, enum.Enum):
    """Derived from started_on / due_date / completed_on — see lifecycle_of.
    Deliberately NOT persisted as a mutable column (approved design §2)."""

    in_progress = "IN_PROGRESS"
    due_today = "DUE_TODAY"
    overdue = "OVERDUE"
    completed_on_time = "COMPLETED_ON_TIME"
    completed_late = "COMPLETED_LATE"


# ---------- pure lifecycle math (no DB) ------------------------------------
def compute_due_date(started_on: date, target_days: int) -> date:
    """Fixed deadline in CALENDAR days, start day counting as day 1:
    due = started_on + (target_days - 1). target_days is clamped to >= 1 so a
    blank/zero benchmark period can never push the deadline before the start."""
    return started_on + timedelta(days=max(1, target_days) - 1)


def lifecycle_of(
    due_date: date, completed_on: date | None, *, today: date | None = None
) -> WorkItemLifecycle:
    today = today or date.today()
    if completed_on is not None:
        return (
            WorkItemLifecycle.completed_late
            if completed_on > due_date
            else WorkItemLifecycle.completed_on_time
        )
    if today < due_date:
        return WorkItemLifecycle.in_progress
    if today == due_date:
        return WorkItemLifecycle.due_today
    return WorkItemLifecycle.overdue


def days_overdue_of(
    due_date: date, completed_on: date | None, *, today: date | None = None
) -> int:
    """Days past the deadline for an OPEN item; 0 once completed or not yet due."""
    today = today or date.today()
    if completed_on is not None or today <= due_date:
        return 0
    return (today - due_date).days


def mirror_fields(item: WorkItem, report_date: date) -> dict:
    """The legacy work_report_tasks columns a linked row mirrors from its work
    item, evaluated for the row's own report date.

    Row-level completion is deliberately per-report: is_completed/completed_date
    mean "the overall task was completed ON THIS report's date" (this row IS the
    completion row), NOT merely that the item is completed somewhere. So an
    earlier daily entry of a task finished on a later report stays is_completed =
    False. started_date/due_date are the item's frozen values, shared by every
    entry. The authoritative overall completion lives on WorkItem.completed_on."""
    completed_here = item.completed_on is not None and item.completed_on == report_date
    return {
        "started_date": item.started_on,
        "due_date": item.due_date,
        "is_completed": completed_here,
        "completed_date": item.completed_on if completed_here else None,
    }


def has_later_linked_entry(
    db: Session, *, item_id: uuid.UUID, report_date: date
) -> bool:
    """True when the work item has a linked daily entry dated AFTER report_date.
    Used to stop an earlier report from completing (backdating) a task that has
    already been continued on a later report."""
    n = db.execute(
        select(func.count())
        .select_from(WorkReportTask)
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .where(
            WorkReportTask.work_item_id == item_id,
            DailyWorkReport.report_date > report_date,
        )
    ).scalar_one()
    return n > 0


def _guard_complete_here(db: Session, *, item: WorkItem, report_date: date) -> None:
    """Shared rule for both completion paths: this report may only be the one that
    completes the task if it isn't already completed on a different report and no
    later continuation exists (which would make completing here a backdate)."""
    if item.completed_on is not None and item.completed_on != report_date:
        raise AppError(
            "validation_error",
            "This task was already completed on another report and cannot be "
            "completed again here.",
            422,
        )
    if has_later_linked_entry(db, item_id=item.id, report_date=report_date):
        raise AppError(
            "validation_error",
            "This task has been continued in a later report. Complete it on the "
            "most recent report instead.",
            422,
        )


def completion_report_ids(
    db: Session, item_ids: set[uuid.UUID]
) -> dict[uuid.UUID, uuid.UUID]:
    """Map each COMPLETED work item id -> the report_id whose report_date equals
    the item's completed_on (the report where completion actually occurred), so
    an earlier report can link to "where this task was completed"."""
    if not item_ids:
        return {}
    rows = db.execute(
        select(WorkItem.id, WorkReportTask.report_id)
        .join(WorkReportTask, WorkReportTask.work_item_id == WorkItem.id)
        .join(DailyWorkReport, DailyWorkReport.id == WorkReportTask.report_id)
        .where(
            WorkItem.id.in_(item_ids),
            WorkItem.completed_on.is_not(None),
            DailyWorkReport.report_date == WorkItem.completed_on,
        )
    ).all()
    return {iid: rid for iid, rid in rows}


# ---------- resolve a task row to a work item on save ----------------------
def _fetch_item(db: Session, work_item_id: uuid.UUID) -> WorkItem:
    item = db.get(WorkItem, work_item_id)
    if item is None:
        raise AppError("validation_error", "The task to continue no longer exists.", 422)
    return item


def resolve_task_work_item(
    db: Session,
    *,
    report: DailyWorkReport,
    task_in,
    snap: dict,
    editable: bool,
    seen: set[uuid.UUID],
    existing_links: set[uuid.UUID] | None = None,
) -> dict:
    """Decide the work-item link + mirrored date/completion fields for one saved
    TASK_BASED task row. Returns a dict of WorkReportTask kwargs:
    work_item_id, started_date, due_date, is_completed, completed_date.

    Two paths:
      START  — task_in.work_item_id is None: create a fresh work item
               (started_on = report date, target_days snapshot, due frozen).
      LINK   — task_in.work_item_id set: validate ownership/project/sub/date,
               attach a new daily entry to the SAME work item, never resetting
               its started_on / due_date.

    `existing_links` are the work items this report ALREADY linked before this
    save (empty on create). A LINK whose id is in that set is a re-save of an
    existing entry, not a brand-new continuation, so the "already completed"
    guard is skipped — editing the originating draft after the item was completed
    on another report must not be blocked.

    Duplicate work_item_id within one report is rejected via `seen`.
    Only ever called for TASK_BASED rows with the feature flag ON.
    """
    existing_links = existing_links or set()
    work_item_id = getattr(task_in, "work_item_id", None)
    is_completed = bool(getattr(task_in, "is_completed", False))

    if work_item_id is None:
        # START — a new lifecycle. target_days snapshotted (>= 1); the benchmark
        # master changing later must not move this deadline.
        target_days = max(1, int(snap.get("benchmark_period_days") or 1))
        started_on = report.report_date
        item = WorkItem(
            employee_id=report.employee_id,
            project_id=task_in.project_id,
            sub_activity_id=task_in.sub_activity_id,
            started_on=started_on,
            target_days=target_days,
            due_date=compute_due_date(started_on, target_days),
            completed_on=started_on if is_completed else None,
            activity_name=snap.get("activity_name"),
            sub_activity_name=snap.get("sub_activity_name"),
            project_code=snap.get("project_code"),
            project_name=snap.get("project_name"),
        )
        db.add(item)
        db.flush()  # assign item.id for the row FK
        return {"work_item_id": item.id, **mirror_fields(item, report.report_date)}

    # LINK — continue an existing work item.
    if work_item_id in seen:
        raise AppError(
            "validation_error",
            "The same task appears twice in this report. Continue a task only once per day.",
            422,
        )
    seen.add(work_item_id)

    item = _fetch_item(db, work_item_id)
    if item.employee_id != report.employee_id:
        raise AppError("forbidden", "You can only continue your own tasks.", 403)
    if item.project_id != task_in.project_id:
        raise AppError(
            "validation_error", "A continued task must keep the same project.", 422
        )
    if item.sub_activity_id != task_in.sub_activity_id:
        raise AppError(
            "validation_error", "A continued task must keep the same sub-activity.", 422
        )
    if report.report_date < item.started_on:
        raise AppError(
            "validation_error",
            "A report cannot be dated before the task started.",
            422,
        )
    # A brand-NEW continuation entry may not attach to an already-completed item.
    # A re-save of an entry this report already had (id in existing_links) is
    # exempt — editing the originating/owning draft must still work, and it may
    # correct its own draft completion via _apply_completion below.
    is_resave = work_item_id in existing_links
    if item.completed_on is not None and not is_resave:
        raise AppError(
            "validation_error",
            "This task is already completed and cannot be continued.",
            422,
        )

    _apply_completion(db, item, is_completed=is_completed, report=report, editable=editable)
    return {"work_item_id": item.id, **mirror_fields(item, report.report_date)}


def _apply_completion(
    db: Session,
    item: WorkItem,
    *,
    is_completed: bool,
    report: DailyWorkReport,
    editable: bool,
) -> None:
    """Completion transitions for a LINK save (checkbox on the report form).

    Completing stamps completed_on = this report's date, but only when the task
    is genuinely completable here: not already completed on another report and
    with no later continuation (see _guard_complete_here) -- an old report must
    never backdate a task finished on a later one. Completing is one-way after
    submission; correcting is allowed only while the report is still an editable
    draft AND it was this very report that completed the item (§9/§10)."""
    if is_completed:
        _guard_complete_here(db, item=item, report_date=report.report_date)
        if item.completed_on is None:
            # completed_on = this report's date (§9). Guaranteed >= started_on by
            # the report_date >= started_on check in resolve_task_work_item.
            item.completed_on = report.report_date
        # already completed on THIS date: idempotent no-op (the guard proved it
        # isn't a different-report completion).
        return

    # Unchecking. Only correct a completion made on THIS editable report.
    if item.completed_on is not None:
        if editable and item.completed_on == report.report_date:
            item.completed_on = None
        # otherwise leave it completed — a submitted/other-report completion is
        # not reopened here (use the completion endpoint's explicit error path).


# ---------- update-flow reconciliation (removed rows) ----------------------
def reconcile_removed_links(
    db: Session,
    *,
    report_date: date,
    removed_item_ids: set[uuid.UUID],
) -> None:
    """During an update/delete the report's task rows are removed and (for an
    update) recreated. For any work item that WAS linked in this report but is no
    longer referenced by it:

      * if this report is the item's originating entry (report_date == started_on)
        and OTHER reports still continue it -> block: beheading the start would
        strip the continuations of their fixed deadline.
      * if nothing else references it anywhere -> delete the now-orphaned item.
      * otherwise (a plain continuation entry removed) -> allow; the work item and
        its other entries are untouched.

    Must be called AFTER the old rows are deleted and the new ones inserted, so
    the reference counts reflect the final state.
    """
    for item_id in removed_item_ids:
        item = db.get(WorkItem, item_id)
        if item is None:
            continue
        remaining = db.execute(
            select(func.count())
            .select_from(WorkReportTask)
            .where(WorkReportTask.work_item_id == item_id)
        ).scalar_one()
        if remaining == 0:
            # No entry references it anywhere — clean up rather than orphan.
            db.delete(item)
            continue
        if item.started_on == report_date:
            raise AppError(
                "validation_error",
                "This task was started in this report and is continued in later "
                "reports. Remove the later continuations first.",
                422,
            )


def linked_item_ids_for_report(db: Session, report_id: uuid.UUID) -> set[uuid.UUID]:
    """work_item_ids currently linked by this report's task rows."""
    rows = db.execute(
        select(WorkReportTask.work_item_id).where(
            WorkReportTask.report_id == report_id,
            WorkReportTask.work_item_id.is_not(None),
        )
    ).scalars().all()
    return {wid for wid in rows if wid is not None}


# ---------- completion endpoint helper -------------------------------------
def complete_via_endpoint(
    db: Session,
    *,
    item: WorkItem,
    is_completed: bool,
    report_date: date,
    report_editable: bool,
) -> None:
    """Completion toggle from PATCH /work-reports/tasks/{id}/completion for a
    linked row. Behaviour is identical to a report-form completion:

      * completing stamps completed_on = THIS row's report date, but only on an
        editable report, only while the task is open, and only when this is a
        valid completion point (not already completed elsewhere, no later
        continuation to backdate over);
      * reopening is allowed only on the report that actually completed the task
        and only while that report is still editable (one-way after submit).

    The caller mirrors just THIS row from the item afterwards -- it must NOT
    propagate is_completed to sibling rows (row-level completion is per report)."""
    if is_completed:
        if item.completed_on is not None:
            if item.completed_on == report_date:
                return  # idempotent — already completed here
            raise AppError(
                "validation_error",
                "This task was already completed on another report and cannot be "
                "completed again here.",
                422,
            )
        if not report_editable:
            raise AppError(
                "validation_error",
                "This report is submitted; complete the task on an editable "
                "report instead.",
                422,
            )
        _guard_complete_here(db, item=item, report_date=report_date)
        item.completed_on = report_date
        return

    # Reopening.
    if item.completed_on is None:
        return  # already open — no-op
    if item.completed_on != report_date:
        raise AppError(
            "validation_error",
            "This task was completed on a different report; reopen it there.",
            422,
        )
    if not report_editable:
        raise AppError(
            "validation_error",
            "This task is already completed and its report is submitted. "
            "Completed tasks cannot be reopened.",
            422,
        )
    item.completed_on = None


# ---------- open-task query (behind the endpoint) --------------------------
_LIFECYCLE_ORDER = {
    WorkItemLifecycle.overdue: 0,
    WorkItemLifecycle.due_today: 1,
    WorkItemLifecycle.in_progress: 2,
}


def get_open_work_items(
    db: Session, *, employee_id: uuid.UUID, report_date: date
) -> list[dict]:
    """Unfinished work items the employee can continue in a report dated
    `report_date`. Lifecycle/overdue are evaluated relative to report_date (the
    report being written), not wall-clock today. Legacy NULL-linked rows are not
    represented here — only real work items. Ordered OVERDUE, DUE_TODAY, then
    IN_PROGRESS by nearest due date."""
    stmt = (
        select(WorkItem, ActivityMaster.parent_id.label("activity_id"))
        .join(ActivityMaster, ActivityMaster.id == WorkItem.sub_activity_id)
        .where(
            WorkItem.employee_id == employee_id,
            WorkItem.completed_on.is_(None),
            WorkItem.started_on <= report_date,
        )
    )
    rows = db.execute(stmt).all()

    out: list[dict] = []
    for item, activity_id in rows:
        lc = lifecycle_of(item.due_date, item.completed_on, today=report_date)
        out.append({
            "work_item_id": item.id,
            "project_id": item.project_id,
            "project_code": item.project_code,
            "project_name": item.project_name,
            "activity_id": activity_id,
            "activity_name": item.activity_name,
            "sub_activity_id": item.sub_activity_id,
            "sub_activity_name": item.sub_activity_name,
            "started_on": item.started_on,
            "due_date": item.due_date,
            "target_days": item.target_days,
            "lifecycle": lc.value,
            "days_overdue": days_overdue_of(
                item.due_date, item.completed_on, today=report_date
            ),
        })
    out.sort(key=lambda r: (
        _LIFECYCLE_ORDER.get(WorkItemLifecycle(r["lifecycle"]), 9),
        r["due_date"],
    ))
    return out
