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

Two different meanings of "duration" live here, deliberately:

  * due_date — a CALENDAR deadline, frozen at creation (started_on plus
    target_days - 1 working days). It is history: it drives on-time vs late
    completion and every historical reader/export, and never moves.
  * allowed duration for a LUMP-SUM activity — counted in WORK DAYS: the
    number of distinct report dates on which the employee actually worked on
    that activity. Skipped calendar days consume nothing, so a 2-day lump-sum
    started on the 25th and worked again on the 30th is still on day 2. Only
    the next work day after the allowance is used up needs Project Head
    continuation approval. See count_work_days / lumpsum_lifecycle below.

TASK_WITH_QUANTITY items are never measured in work days — they keep the
calendar due_date lifecycle exactly as before.
"""
import enum
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.activity_master.service import compute_week_bounds
from app.modules.calendar.working_days import add_working_days
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
def compute_due_date(db: Session, started_on: date, target_days: int) -> date:
    """Fixed deadline in WORKING days, start day counting as day 1: a 1-day
    allowed duration is due the same day it starts; a 2-day duration is due
    the NEXT working day (weekends/company holidays skipped by
    calendar.working_days.add_working_days), and so on. target_days is
    clamped to >= 1 so a blank/zero benchmark period can never push the
    deadline before the start.

    Falls back to started_on itself if the company calendar cannot resolve a
    working day within the lookahead window (a misconfigured calendar) rather
    than raising mid-save — this should never happen in practice."""
    steps = max(1, target_days) - 1
    due = add_working_days(db, started_on, steps)
    return due if due is not None else started_on


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


# ---------- lump-sum work-day usage (the allowed-duration rule) ------------
def work_day_dates_by_item(
    db: Session, item_ids
) -> dict[uuid.UUID, set[date]]:
    """The distinct report dates each work item has actually been worked on.

    This set — not the calendar span — is the whole raw material of the lump-sum
    allowed-duration rule, and it is fetched in ONE place so every reader of
    "work days" is reading the same thing. A day with no entry for the item is
    simply not in the set and consumes nothing.

    Items with no entry at all are absent from the mapping (read them as an
    empty set). The sets are small by construction: an item lives inside a
    single Friday-Thursday reporting week.
    """
    ids = list(item_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(WorkReportTask.work_item_id, DailyWorkReport.report_date)
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .where(WorkReportTask.work_item_id.in_(ids))
        .distinct()
    ).all()
    out: dict[uuid.UUID, set[date]] = {}
    for wid, d in rows:
        out.setdefault(wid, set()).add(d)
    return out


def count_work_days_by_item(
    db: Session, item_ids, *, excluding: date | None = None
) -> dict[uuid.UUID, int]:
    """How many work days each item has spent, over work_day_dates_by_item.

    `excluding` drops one report date from the count, always the report being
    written: a day is consumed by having been worked, and the day under
    consideration is not consumed yet. It also makes the count independent of
    whether the caller has already inserted/deleted that report's own rows.

    Items with no entry at all are absent from the mapping (read them as 0); an
    item left with nothing after `excluding` reports 0 explicitly."""
    return {
        wid: sum(1 for d in dates if d != excluding)
        for wid, dates in work_day_dates_by_item(db, item_ids).items()
    }


def count_work_days(
    db: Session, *, item_id: uuid.UUID, excluding: date | None = None
) -> int:
    """count_work_days_by_item for a single item — see it for the rule."""
    return count_work_days_by_item(db, [item_id], excluding=excluding).get(item_id, 0)


def days_used_before(dates, report_date: date) -> int:
    """Work days a lump-sum item had already spent BEFORE `report_date`, from an
    already-fetched date set (work_day_dates_by_item).

    Same quantity, and the same convention, as
    count_work_days(excluding=report_date) returns for the report being written
    — days consumed before the day under consideration — so it feeds
    lumpsum_lifecycle / lumpsum_allowance_exhausted / lumpsum_days_over
    unchanged. It exists so a whole page of ALREADY-SAVED rows, each with its
    own report date, can be positioned in its item's allowance from one query
    instead of one query per row.

    Strictly earlier dates, deliberately: a saved row's place in the allowance
    is decided by the days worked before it. Counting later continuations too
    (what `excluding` does) would retroactively push an early, within-allowance
    row into "duration exceeded" the moment the activity was continued again."""
    return sum(1 for d in dates if d < report_date)


def lumpsum_flags_by_item(db: Session, item_ids) -> dict[uuid.UUID, bool]:
    """Which of these work items are LUMP-SUM — the ones measured in work days
    rather than against the calendar due_date. Resolved from the sub-activity's
    live Activity Master row through the one shared predicate
    (activity_master.models.is_lumpsum_unit_row), never re-derived from a row
    snapshot: benchmark_type_snapshot is written at submit, so a draft row has
    none and would silently read as non-lump-sum."""
    from app.modules.activity_master.models import is_lumpsum_unit_row

    ids = list(item_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            WorkItem.id,
            ActivityMaster.benchmark_type,
            ActivityMaster.relevant_count_field,
        )
        .join(ActivityMaster, ActivityMaster.id == WorkItem.sub_activity_id)
        .where(WorkItem.id.in_(ids))
    ).all()
    return {iid: is_lumpsum_unit_row(btype, rcf) for iid, btype, rcf in rows}


def lumpsum_allowance_exhausted(days_used: int, target_days: int) -> bool:
    """Whether a lump-sum item has already spent its allowed duration, so the
    NEXT work day on it needs continuation approval. `days_used` counts work
    days consumed BEFORE the day being considered (count_work_days with
    excluding=that date). target_days is clamped to >= 1 exactly as
    compute_due_date clamps it, so a blank benchmark period still grants one
    work day."""
    return days_used >= max(1, target_days)


def lumpsum_lifecycle(days_used: int, target_days: int) -> WorkItemLifecycle:
    """Lifecycle of an OPEN lump-sum item relative to the report being written,
    in work days rather than calendar days:

      IN_PROGRESS — work days remain after this one.
      DUE_TODAY   — this is the last day of the allowed duration.
      OVERDUE     — the allowance is spent; continuing needs approval.

    Completed items never reach here (get_open_work_items filters them out) —
    on-time vs late completion stays a CALENDAR question, answered by
    lifecycle_of against the frozen due_date."""
    allowed = max(1, target_days)
    if days_used >= allowed:
        return WorkItemLifecycle.overdue
    if days_used == allowed - 1:
        return WorkItemLifecycle.due_today
    return WorkItemLifecycle.in_progress


def lumpsum_days_over(days_used: int, target_days: int) -> int:
    """Work days already taken BEYOND the allowed duration — the work-day
    counterpart of days_overdue_of. 0 while the allowance holds, and still 0 on
    the first blocked day (nothing beyond it has been worked yet); it only
    grows once approved continuation days are actually used."""
    return max(0, days_used - max(1, target_days))


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


def has_pending_continuation(db: Session, *, work_item_id: uuid.UUID) -> bool:
    """Whether a continuation request for this work item is still awaiting a
    Project Head decision. Lives here (rather than being inlined at the two call
    sites) so "is this item's continuation undecided?" has one answer."""
    from app.modules.continuation_requests.service import pending_request_for_work_item

    return pending_request_for_work_item(db, work_item_id) is not None


PENDING_CONTINUATION_MESSAGE = (
    "This activity's continuation is awaiting Project Head approval. "
    "You can mark it complete once the continuation is approved."
)


def _guard_complete_here(db: Session, *, item: WorkItem, report_date: date) -> None:
    """Shared rule for both completion paths: this report may only be the one that
    completes the task if it isn't already completed on a different report and no
    later continuation exists (which would make completing here a backdate).

    An undecided continuation deliberately does NOT live here. It is a rule about
    ONE ACTIVITY ("this activity can't be marked complete yet"), not about the
    report ("this report can't be submitted"), and the two call sites need
    opposite handling of it:

      * _apply_completion (report save) SKIPS the completion and lets the report
        submit - raising there aborted the whole multi-activity save, which is
        the bug this correction fixes;
      * complete_via_endpoint (an explicit, single-purpose "mark complete"
        request) raises, because refusing the one action the caller asked for is
        the honest answer.

    Both consult has_pending_continuation directly, so "is this item's
    continuation undecided?" still has exactly one answer."""
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
    new_continuation_requests: list | None = None,
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

    `new_continuation_requests`, when passed, is an accumulator list the
    caller (work_reports.service) owns for the whole report save: a brand-new
    continuation of an over-allowance lump-sum item auto-creates a pending
    ContinuationRequest (see the "Lump-sum continuation approval" block
    below) and appends it here so the caller can fire its
    'continuation_requested' notification AFTER the report's own transaction
    commits — this function itself never commits and never notifies.
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
            due_date=compute_due_date(db, started_on, target_days),
            completed_on=started_on if is_completed else None,
            activity_name=snap.get("activity_name"),
            sub_activity_name=snap.get("sub_activity_name"),
            project_code=snap.get("project_code"),
            project_name=snap.get("project_name"),
        )
        db.add(item)
        db.flush()  # assign item.id for the row FK
        # A fresh item is on day 1 of its allowance — nothing to approve.
        return {
            "work_item_id": item.id,
            "continuation_request_id": None,
            **mirror_fields(item, report.report_date),
        }

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

    # Lump-sum continuation approval. Only once the item's allowed duration is
    # spent in WORK DAYS, and only for lump-sum rows — TASK_WITH_QUANTITY rows
    # (snap["is_lumpsum_task"] is False for them) are never touched.
    #
    # A rejected continuation stays blocked (403) — the employee gets no
    # benefit from an unapproved continuation. Otherwise (no request yet, or
    # one still pending) the save PROCEEDS and a pending request is
    # auto-created if one doesn't already exist — the employee is never locked
    # out of entering today's work while a decision is pending. What the save
    # does NOT do is make that work accepted: the row is stamped with the
    # governing request's id, so its approval state is read straight off the
    # request (pending / approved) and a later rejection can withdraw exactly
    # these rows. An approved request proceeds exactly as before.
    #
    # Only a brand-NEW continuation entry is GATED (a resave of a row this
    # report already had must not be blocked), but the STAMP is resolved for
    # resaves too: the report's rows are deleted and rewritten on every update,
    # so skipping the stamp on a resave would quietly detach an already-pending
    # continuation from its decision.
    continuation_request_id = None
    if snap.get("is_lumpsum_task"):
        days_used = count_work_days(
            db, item_id=item.id, excluding=report.report_date
        )
        if lumpsum_allowance_exhausted(days_used, item.target_days):
            from app.modules.continuation_requests.service import (
                get_or_create_pending_for_continuation,
                latest_request_for_work_item,
            )

            latest = latest_request_for_work_item(db, item.id)
            if not is_resave:
                if latest is not None and latest.status == "rejected":
                    raise AppError(
                        "forbidden",
                        "The Project Head rejected continuation of this "
                        "activity beyond its allowed duration. It cannot be "
                        "continued further.",
                        403,
                    )
                if latest is None or latest.status == "pending":
                    req, created = get_or_create_pending_for_continuation(
                        db, item=item, continuation_date=report.report_date,
                    )
                    if created and new_continuation_requests is not None:
                        new_continuation_requests.append(req)
                    latest = req
                # latest.status == "approved": nothing to do, save proceeds.
            # A request governs every row dated on or after the day it was
            # raised. Earlier rows are within-allowance work that never needed
            # a decision and must stay untouched by one.
            if (
                latest is not None
                and latest.status != "rejected"
                and report.report_date >= latest.continuation_date
            ):
                continuation_request_id = latest.id

    _apply_completion(db, item, is_completed=is_completed, report=report, editable=editable)
    return {
        "work_item_id": item.id,
        "continuation_request_id": continuation_request_id,
        **mirror_fields(item, report.report_date),
    }


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
    draft AND it was this very report that completed the item (§9/§10).

    A tick on an activity whose continuation is still undecided is IGNORED, not
    rejected: the day's work is saved, the report submits, and the activity stays
    open until the Project Head decides. Refusing the whole save here is what
    used to make one pending lump-sum continuation block an entire multi-activity
    report. The row still says what happened - it is stamped with the request, so
    the editor and the detail page both label it "Continuation requested -
    awaiting Project Head approval" - and the UI disables the checkbox for the
    same reason, so this is a backstop, not the primary signal."""
    if is_completed:
        if has_pending_continuation(db, work_item_id=item.id):
            return
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

    Unlike the report-save path, an undecided continuation RAISES here: this
    endpoint's whole payload is "mark this activity complete", so there is
    nothing else to save and silently doing nothing would be a lie. Nothing about
    the report's own submitted state is touched either way.

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
        if has_pending_continuation(db, work_item_id=item.id):
            raise AppError("validation_error", PENDING_CONTINUATION_MESSAGE, 422)
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
    IN_PROGRESS by nearest due date.

    Continuation is confined to a SINGLE Friday-Thursday reporting week, for
    EVERY kind of work item, lump-sum included: an item may be continued only
    within the week that contains its originating started_on. Once report_date
    crosses into a later week the item drops out of the suggestions (it stays
    incomplete in the DB and keeps appearing as Not-Completed/Overdue in
    historical benchmark exports — see project rule). Re-selecting the same
    activity in the new week starts a fresh work item.

    That weekly boundary is intentional product behaviour and is not something
    the work-day rule below overrides. Work-day counting decides how much of the
    allowed duration a lump-sum activity has spent WITHIN its reporting week —
    it does not extend the activity past the end of that week. The consequence
    is deliberate: an incomplete lump-sum item is not carried forward, and an
    employee who re-picks the activity next week gets a new work item with a new
    allowance for that week. Continuation approval therefore governs continuing
    an activity inside its own reporting week.

    Lump-sum items are measured in WORK DAYS, not calendar days: lifecycle and
    days_overdue come from lumpsum_lifecycle/lumpsum_days_over over the count of
    distinct dates the item has actually been worked on (excluding report_date,
    which is not consumed until it is worked). So a lump-sum item whose calendar
    due date has long passed still reads IN_PROGRESS/DUE_TODAY while allowed
    work days remain, and OVERDUE means "allowance spent - the next work day
    needs approval". A TASK_WITH_QUANTITY item keeps the calendar due_date
    lifecycle unchanged.

    Lump-sum continuation approval: an OVERDUE item whose sub-activity is a
    lump-sum/NON_QUANTITATIVE task (no relevant_count_field - see
    activity_master.models.is_lumpsum_unit_row) additionally carries
    requires_continuation_approval / continuation_status / continuation_request_id
    / continuation_routed_to, resolved from continuation_requests. A
    TASK_WITH_QUANTITY item is never gated - those four fields stay
    False/None/None/None for it. `is_lumpsum` is published on every row so the
    form can tell the two presentations apart without re-deriving the rule."""
    from app.modules.activity_master.models import is_lumpsum_unit_row

    # The reporting week of the report being written; only items whose own start
    # week matches this may be continued (compute_week_bounds is the shared
    # Fri-Thu calc used everywhere else, so continuation and benchmarks never
    # diverge).
    report_cycle = compute_week_bounds(report_date)
    stmt = (
        select(
            WorkItem,
            ActivityMaster.parent_id.label("activity_id"),
            ActivityMaster.benchmark_type.label("benchmark_type"),
            ActivityMaster.relevant_count_field.label("relevant_count_field"),
        )
        .join(ActivityMaster, ActivityMaster.id == WorkItem.sub_activity_id)
        .where(
            WorkItem.employee_id == employee_id,
            WorkItem.completed_on.is_(None),
            WorkItem.started_on <= report_date,
        )
    )
    rows = db.execute(stmt).all()

    candidates: list[tuple[WorkItem, uuid.UUID | None, bool]] = []
    for item, activity_id, benchmark_type, relevant_count_field in rows:
        # Confine to the item's own reporting week — lump-sum items included.
        # started_on is the frozen originating date (never the latest
        # continuation), so a task started last Friday stops being suggested the
        # moment report_date rolls into the next Friday-Thursday window.
        if compute_week_bounds(item.started_on) != report_cycle:
            continue
        candidates.append((
            item, activity_id, is_lumpsum_unit_row(benchmark_type, relevant_count_field),
        ))

    # Work days each item has already consumed, this report's own date excluded
    # (it is not spent until it is worked). Resolved for every item so days_used
    # is honest on the wire; only lump-sum items are MEASURED by it.
    used_by_item = count_work_days_by_item(
        db, [item.id for item, _, _ in candidates], excluding=report_date
    )

    out: list[dict] = []
    lumpsum_ids: set[uuid.UUID] = set()
    for item, activity_id, is_lumpsum in candidates:
        days_used = used_by_item.get(item.id, 0)
        if is_lumpsum:
            lumpsum_ids.add(item.id)
            lc = lumpsum_lifecycle(days_used, item.target_days)
            days_over = lumpsum_days_over(days_used, item.target_days)
        else:
            lc = lifecycle_of(item.due_date, item.completed_on, today=report_date)
            days_over = days_overdue_of(
                item.due_date, item.completed_on, today=report_date
            )
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
            "days_used": days_used,
            "is_lumpsum": is_lumpsum,
            "lifecycle": lc.value,
            "days_overdue": days_over,
            "requires_continuation_approval": False,
            "continuation_status": None,
            "continuation_request_id": None,
            "continuation_routed_to": None,
        })
    out.sort(key=lambda r: (
        _LIFECYCLE_ORDER.get(WorkItemLifecycle(r["lifecycle"]), 9),
        r["due_date"],
    ))

    overdue_lumpsum_ids = {
        r["work_item_id"] for r in out
        if r["work_item_id"] in lumpsum_ids and r["lifecycle"] == WorkItemLifecycle.overdue.value
    }
    if overdue_lumpsum_ids:
        from app.modules.continuation_requests.service import latest_requests_by_work_item

        latest = latest_requests_by_work_item(db, overdue_lumpsum_ids)
        for r in out:
            if r["work_item_id"] not in overdue_lumpsum_ids:
                continue
            req = latest.get(r["work_item_id"])
            if req is None:
                r["requires_continuation_approval"] = True
                continue
            r["continuation_request_id"] = req.id
            r["continuation_status"] = req.status
            r["requires_continuation_approval"] = req.status != "approved"
            r["continuation_routed_to"] = req.routed_to_name
    return out
