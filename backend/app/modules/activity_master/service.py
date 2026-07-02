"""ActivityMaster service — admin CRUD (Activity + Sub-Activity) + benchmark calc.

RBAC for mutations is enforced in the router (require_role("project_manager")),
mirroring activity_types. This module just enforces the data-shape rules that
don't belong in the router: parent/level consistency, NUMERIC requiring a value,
and that benchmark_* fields are never set on a level='activity' row.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.modules.activity_master.models import (
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    ActivityMaster,
)
from app.modules.activity_master.schemas import (
    ActivityCreate,
    ActivityMasterUpdate,
    SubActivityCreate,
)
from app.shared.errors import AppError

_BENCHMARK_FIELDS = (
    "benchmark_type", "benchmark_value", "benchmark_period_days",
    "benchmark_unit_note", "benchmark_remarks", "relevant_count_field",
)


def compute_benchmark(
    benchmark_type: str | None,
    benchmark_value: Decimal | float | None,
    actual_value: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Returns (deficit, productivity_pct). NUMERIC only — TASK_BASED and no-
    benchmark rows never get a deficit/productivity calculation, by design.

    `actual_value` is whichever of the work report task's existing
    tags_count/docs_count/bom_count/spares_count the sub-activity's
    relevant_count_field points to — there's no separate "actual count" entry,
    by design (callers must not enter the same production number twice)."""
    if benchmark_type != "NUMERIC" or benchmark_value is None:
        return None, None
    value = Decimal(str(benchmark_value))
    if value == 0:
        return None, None
    actual = Decimal(actual_value or 0)
    deficit = max(Decimal("0"), value - actual)
    productivity_pct = (actual / value) * 100
    return deficit, productivity_pct


def compute_overdue(
    due_date: date | None, is_completed: bool, today: date | None = None,
) -> tuple[bool, int]:
    """Returns (is_overdue, days_overdue) for a TASK_BASED row. Computed
    fresh on every call (never stored) so it's always relative to the
    current date rather than stale from whenever it was last checked.

    A completed task, or one with no due_date at all (no benchmark tracked),
    is never overdue."""
    if is_completed or due_date is None:
        return False, 0
    today = today or date.today()
    if today <= due_date:
        return False, 0
    return True, (today - due_date).days


def compute_week_bounds(reference_date: date) -> tuple[date, date]:
    """Mon-Fri bounds of the week containing reference_date."""
    monday = reference_date - timedelta(days=reference_date.weekday())
    friday = monday + timedelta(days=4)
    return monday, friday


def get_daily_benchmark_ledger(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Live (never stored) daily benchmark ledger for NUMERIC sub-activities:
    one row per (date, employee, sub_activity) the employee *actually
    submitted* this week (Mon..Fri). daily_target is a flat benchmark_value
    (not multiplied by elapsed days), daily_pending = max(0, target - actual)
    is clamped PER DAY — a surplus on one day is never carried forward to
    offset a deficit on another, by design (a good Thursday shouldn't erase a
    bad Wednesday). Weekly totals are a plain sum of these daily rows,
    computed by the caller.

    Only days with a real submission produce a row: a skipped day is simply
    absent rather than synthesized as a zero-actual / full-pending row, so
    benchmark performance reflects only activities actually reported. Any
    shortfall on a reported day stays on that day's own record (its
    `pending`); it is never spread across artificial Mon/Tue/Thu rows.
    Always re-read from the DB, so resubmits never double count.

    Grouped by (employee, sub_activity) only, not by project — the benchmark
    target is per employee per activity, not per employee per activity per
    project. `project_name`/`hours_minutes` are reported per row purely for
    display (the Homepage Alerts benchmark cards) — a day can have multiple
    task rows for the same sub-activity (e.g. split across projects), so
    those are summed/joined in Python rather than the benchmark math, which
    stays keyed on actual/target only."""
    from app.modules.work_reports.models import (
        DailyWorkReport,
        DayStatus,
        WorkReportStatus,
        WorkReportTask,
    )

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)

    actual_expr = case(
        (ActivityMaster.relevant_count_field == "tags", WorkReportTask.tags_count),
        (ActivityMaster.relevant_count_field == "docs", WorkReportTask.docs_count),
        (ActivityMaster.relevant_count_field == "bom", WorkReportTask.bom_count),
        (ActivityMaster.relevant_count_field == "spares", WorkReportTask.spares_count),
        else_=0,
    )
    hours_expr = func.coalesce(WorkReportTask.minutes_spent, 0) + func.coalesce(
        WorkReportTask.task_minutes_spent, 0
    )

    stmt = (
        select(
            DailyWorkReport.employee_id,
            DailyWorkReport.report_date,
            DailyWorkReport.day_status,
            ActivityMaster.parent_id.label("activity_id"),
            ActivityMaster.id.label("sub_activity_id"),
            ActivityMaster.name.label("sub_activity_name"),
            ActivityMaster.benchmark_value,
            ActivityMaster.relevant_count_field,
            WorkReportTask.project_name,
            WorkReportTask.project_code,
            actual_expr.label("actual"),
            hours_expr.label("hours_minutes"),
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .where(
            DailyWorkReport.status == WorkReportStatus.submitted,
            DailyWorkReport.report_date >= week_start,
            DailyWorkReport.report_date <= week_end,
            ActivityMaster.benchmark_type == "NUMERIC",
        )
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(DailyWorkReport.employee_id.in_(employee_ids))

    rows = db.execute(stmt).all()
    if not rows:
        return []

    # day_by_key[(employee_id, report_date, sub_activity_id)] = {actual, hours_minutes, projects}
    day_by_key: dict[tuple[uuid.UUID, date, uuid.UUID], dict] = {}
    meta: dict[tuple[uuid.UUID, uuid.UUID], dict] = {}
    for r in rows:
        mkey = (r.employee_id, r.sub_activity_id)
        meta[mkey] = {
            "activity_id": r.activity_id,
            "sub_activity_name": r.sub_activity_name,
            "benchmark_value": r.benchmark_value,
            "relevant_count_field": r.relevant_count_field,
        }
        dkey = (r.employee_id, r.report_date, r.sub_activity_id)
        bucket = day_by_key.setdefault(
            dkey,
            {
                "actual": Decimal("0"),
                "hours_minutes": 0,
                "projects": [],
                "project_codes": [],
                # Same for every row of a given (employee, date) report; used to
                # halve the day's target on a half day.
                "day_status": r.day_status,
            },
        )
        bucket["actual"] += Decimal(r.actual or 0)
        bucket["hours_minutes"] += int(r.hours_minutes or 0)
        if r.project_name and r.project_name not in bucket["projects"]:
            bucket["projects"].append(r.project_name)
        if r.project_code and r.project_code not in bucket["project_codes"]:
            bucket["project_codes"].append(r.project_code)

    activity_ids = {m["activity_id"] for m in meta.values() if m["activity_id"]}
    activity_names: dict[uuid.UUID, str] = {}
    if activity_ids:
        activity_names = dict(
            db.execute(
                select(ActivityMaster.id, ActivityMaster.name).where(
                    ActivityMaster.id.in_(activity_ids)
                )
            ).all()
        )

    out = []
    for (employee_id, d, sub_activity_id), bucket in day_by_key.items():
        m = meta[(employee_id, sub_activity_id)]
        target = Decimal(str(m["benchmark_value"] or 0))
        # Half day -> the day's target (and therefore its pending) is halved.
        if bucket.get("day_status") == DayStatus.half_day:
            target = target / 2
        actual = bucket["actual"]
        project_name = ", ".join(bucket["projects"]) if bucket["projects"] else None
        project_code = ", ".join(bucket["project_codes"]) if bucket["project_codes"] else None
        pending = max(Decimal("0"), target - actual)
        out.append({
            "employee_id": employee_id,
            "date": d,
            "activity_id": m["activity_id"],
            "activity_name": activity_names.get(m["activity_id"]),
            "sub_activity_id": sub_activity_id,
            "sub_activity_name": m["sub_activity_name"],
            "benchmark_unit": m["relevant_count_field"],
            "project_name": project_name,
            "project_code": project_code,
            "hours_minutes": bucket["hours_minutes"],
            "target": target,
            "actual": actual,
            "pending": pending,
        })
    out.sort(key=lambda r: (r["date"], r["sub_activity_name"]))
    return out


def get_overdue_activities(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Live (never stored) list of TASK_BASED work-report-task rows whose
    due_date has passed and which are not completed. due_date/is_completed
    are set at draft save (not deferred to submit), so this includes draft
    and submitted reports alike — an abandoned draft with a passed due date
    is still overdue.

    Scoped to the CURRENT week (Mon..Fri) like the benchmark ledger: only
    tasks whose due_date falls in this week (week_start <= due_date < today)
    count, so overdue resets every Monday alongside the numeric benchmark
    backlog rather than carrying stale deadlines forward indefinitely."""
    from app.modules.work_reports.models import DailyWorkReport, WorkReportTask

    today = today or date.today()
    week_start, _ = compute_week_bounds(today)

    stmt = (
        select(
            DailyWorkReport.employee_id,
            WorkReportTask.id.label("work_report_task_id"),
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.project_code,
            DailyWorkReport.report_date,
            WorkReportTask.due_date,
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .where(
            ActivityMaster.benchmark_type == "TASK_BASED",
            WorkReportTask.due_date.is_not(None),
            WorkReportTask.due_date >= week_start,
            WorkReportTask.due_date < today,
            WorkReportTask.is_completed.is_(False),
        )
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(DailyWorkReport.employee_id.in_(employee_ids))

    rows = db.execute(stmt).all()
    out = []
    for r in rows:
        _, days_overdue = compute_overdue(r.due_date, False, today)
        out.append({
            "employee_id": r.employee_id,
            "work_report_task_id": r.work_report_task_id,
            "activity_name": r.activity_name,
            "sub_activity_name": r.sub_activity_name,
            "project_code": r.project_code,
            "report_date": r.report_date,
            "due_date": r.due_date,
            "days_overdue": days_overdue,
        })
    return out


def get_task_status_activities(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Live (never stored) list of TASK_BASED rows for the Homepage Alerts
    'Pending Tasks (This Week)' panel: every task whose due_date falls inside
    the current week (week_start <= due_date <= week_end, Mon..Fri), completed
    or not. The employee dashboard is deliberately current-week-only — a task
    from a previous week (whether still pending or long overdue) never appears
    here, even though its row stays in the database. The view resets every
    Monday with the week bounds.

    `status` is "completed" once the task is marked done (so a within-week task
    finished later in the week reads as Completed), otherwise "pending" — we no
    longer surface a separate "due today" state, since the panel is scoped to
    the week rather than to overdue-only rows. `days_overdue` is kept for the
    schema but only non-zero for an uncompleted task already past its due_date
    within this same week (not displayed on the employee card)."""
    from app.modules.work_reports.models import DailyWorkReport, WorkReportTask

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)

    hours_expr = func.coalesce(WorkReportTask.minutes_spent, 0) + func.coalesce(
        WorkReportTask.task_minutes_spent, 0
    )

    stmt = (
        select(
            DailyWorkReport.employee_id,
            WorkReportTask.id.label("work_report_task_id"),
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.project_name,
            WorkReportTask.project_code,
            DailyWorkReport.report_date,
            WorkReportTask.due_date,
            WorkReportTask.completed_date,
            WorkReportTask.is_completed,
            hours_expr.label("hours_minutes"),
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .where(
            ActivityMaster.benchmark_type == "TASK_BASED",
            WorkReportTask.due_date.is_not(None),
            WorkReportTask.due_date >= week_start,
            WorkReportTask.due_date <= week_end,
        )
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(DailyWorkReport.employee_id.in_(employee_ids))

    rows = db.execute(stmt).all()
    out = []
    for r in rows:
        overdue = not r.is_completed and r.due_date < today
        out.append({
            "employee_id": r.employee_id,
            "work_report_task_id": r.work_report_task_id,
            "activity_name": r.activity_name,
            "sub_activity_name": r.sub_activity_name,
            "project_name": r.project_name,
            "project_code": r.project_code,
            "report_date": r.report_date,
            "due_date": r.due_date,
            "completed_date": r.completed_date,
            "hours_minutes": int(r.hours_minutes or 0),
            "status": "completed" if r.is_completed else "pending",
            "days_overdue": (today - r.due_date).days if overdue else 0,
        })
    out.sort(key=lambda r: (r["due_date"], r["sub_activity_name"]))
    return out


def _fetch(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    row = db.get(ActivityMaster, activity_master_id)
    if row is None:
        raise AppError("not_found", "Activity not found.", 404)
    return row


def get_activity_master(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    return _fetch(db, activity_master_id)


def list_activities(db: Session, *, active_only: bool = True) -> list[ActivityMaster]:
    stmt = select(ActivityMaster).where(ActivityMaster.level == LEVEL_ACTIVITY)
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True))
    stmt = stmt.order_by(ActivityMaster.sort_order, ActivityMaster.name)
    return list(db.execute(stmt).scalars().all())


def list_sub_activities(
    db: Session, activity_id: uuid.UUID, *, active_only: bool = True
) -> list[ActivityMaster]:
    _assert_is_activity(db, activity_id)
    stmt = select(ActivityMaster).where(ActivityMaster.parent_id == activity_id)
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True))
    stmt = stmt.order_by(ActivityMaster.sort_order, ActivityMaster.name)
    return list(db.execute(stmt).scalars().all())


def list_all_sub_activities_flat(db: Session, *, active_only: bool = True) -> list[dict]:
    """Every leaf row across every Activity, joined to the parent's name — the
    shape the work-report cascading select ultimately needs."""
    Parent = aliased(ActivityMaster)
    stmt = (
        select(ActivityMaster, Parent.name)
        .join(Parent, ActivityMaster.parent_id == Parent.id)
        .where(ActivityMaster.level == LEVEL_SUB_ACTIVITY)
    )
    if active_only:
        stmt = stmt.where(ActivityMaster.is_active.is_(True), Parent.is_active.is_(True))
    stmt = stmt.order_by(Parent.sort_order, Parent.name, ActivityMaster.sort_order, ActivityMaster.name)
    rows = db.execute(stmt).all()
    return [
        {
            "id": sub.id,
            "activity_id": sub.parent_id,
            "activity_name": parent_name,
            "name": sub.name,
            "benchmark_type": sub.benchmark_type,
            "benchmark_value": sub.benchmark_value,
            "benchmark_period_days": sub.benchmark_period_days,
            "relevant_count_field": sub.relevant_count_field,
            "is_active": sub.is_active,
        }
        for sub, parent_name in rows
    ]


def _assert_is_activity(db: Session, activity_id: uuid.UUID) -> ActivityMaster:
    activity = _fetch(db, activity_id)
    if activity.level != LEVEL_ACTIVITY:
        raise AppError("validation_error", "Not a top-level Activity.", 422)
    return activity


def create_activity(
    db: Session, data: ActivityCreate, *, created_by: uuid.UUID | None = None
) -> ActivityMaster:
    row = ActivityMaster(
        parent_id=None,
        level=LEVEL_ACTIVITY,
        code=data.code,
        name=data.name,
        sort_order=data.sort_order,
        is_active=data.is_active,
        created_by=created_by,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity with this code already exists.", 409)
    db.refresh(row)
    return row


def create_sub_activity(
    db: Session,
    activity_id: uuid.UUID,
    data: SubActivityCreate,
    *,
    created_by: uuid.UUID | None = None,
) -> ActivityMaster:
    _assert_is_activity(db, activity_id)
    row = ActivityMaster(
        parent_id=activity_id,
        level=LEVEL_SUB_ACTIVITY,
        code=data.code,
        name=data.name,
        benchmark_type=data.benchmark_type,
        benchmark_value=data.benchmark_value,
        benchmark_period_days=data.benchmark_period_days,
        benchmark_unit_note=data.benchmark_unit_note,
        benchmark_remarks=data.benchmark_remarks,
        relevant_count_field=data.relevant_count_field,
        sort_order=data.sort_order,
        is_active=data.is_active,
        created_by=created_by,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active sub-activity with this code already exists.", 409)
    db.refresh(row)
    return row


def update_activity_master(
    db: Session, activity_master_id: uuid.UUID, data: ActivityMasterUpdate
) -> ActivityMaster:
    row = _fetch(db, activity_master_id)
    fields = data.model_dump(exclude_unset=True)

    if row.level == LEVEL_ACTIVITY and any(f in fields for f in _BENCHMARK_FIELDS):
        raise AppError(
            "validation_error", "Benchmarks only apply to sub-activities, not activities.", 422
        )

    new_type = fields.get("benchmark_type", row.benchmark_type)
    new_value = fields.get("benchmark_value", row.benchmark_value)
    new_count_field = fields.get("relevant_count_field", row.relevant_count_field)
    if new_type == "NUMERIC":
        if new_value is None:
            raise AppError("validation_error", "benchmark_value is required when benchmark_type is NUMERIC.", 422)
        if new_count_field is None:
            raise AppError(
                "validation_error",
                "relevant_count_field is required when benchmark_type is NUMERIC "
                "(it's the benchmark's actual-value source).",
                422,
            )

    for key, value in fields.items():
        setattr(row, key, value)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "An active activity with this code already exists.", 409)
    db.refresh(row)
    return row


def deactivate_activity_master(db: Session, activity_master_id: uuid.UUID) -> ActivityMaster:
    """Soft-deactivate. Does not cascade to children — an Activity's
    Sub-Activities must be deactivated explicitly, one at a time (Phase 1
    keeps this simple/explicit rather than guessing intent)."""
    row = _fetch(db, activity_master_id)
    row.is_active = False
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
