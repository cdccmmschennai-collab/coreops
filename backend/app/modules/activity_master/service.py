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
    COUNT_FIELD_BY_UNIT,
    DAILY_QUANTITY_BENCHMARK_TYPES,
    LEVEL_ACTIVITY,
    LEVEL_SUB_ACTIVITY,
    QUANTITY_BENCHMARK_TYPES,
    TASK_BENCHMARK_TYPES,
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


def actual_count_expr():
    """SQL expression picking the WorkReportTask count column named by
    ActivityMaster.relevant_count_field.

    Derived from COUNT_FIELD_BY_UNIT so the six units are declared exactly once.
    Every ledger/overdue/cycle query below shares this; previously the same
    four-way case() was hand-repeated in each, which is how a new unit gets
    silently dropped from one of them. else_=0 keeps an unset/unknown unit
    arithmetic rather than NULL."""
    from app.modules.work_reports.models import WorkReportTask

    return case(
        *[
            (ActivityMaster.relevant_count_field == unit, getattr(WorkReportTask, column))
            for unit, column in COUNT_FIELD_BY_UNIT.items()
        ],
        else_=0,
    )


def compute_benchmark(
    benchmark_type: str | None,
    benchmark_value: Decimal | float | None,
    actual_value: int | None,
) -> tuple[Decimal | None, Decimal | None]:
    """Returns (deficit, productivity_pct). QUANTITY modes only (NUMERIC,
    NUMERIC_DAILY, TASK_WITH_QUANTITY) — TASK_STATUS_ONLY / legacy TASK_BASED and
    no-benchmark rows never get a deficit/productivity calculation, by design.

    Membership-tested rather than compared to a literal, so the legacy 'NUMERIC'
    stored on historical rows and in benchmark_type_snapshot keeps working
    identically to the new NUMERIC_DAILY.

    `actual_value` is whichever of the work report task's existing
    tags_count/docs_count/bom_count/spares_count/pages_count/records_count the
    sub-activity's relevant_count_field points to — there's no separate "actual
    count" entry, by design (callers must not enter the same production number
    twice). productivity_pct is deliberately uncapped: 120% must read as 120%."""
    if benchmark_type not in QUANTITY_BENCHMARK_TYPES or benchmark_value is None:
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
    """Fri-Thu bounds of the benchmark cycle containing reference_date.

    The cycle starts on Friday and runs through the following Thursday, so
    the weekly benchmark reset happens every Friday (PMs export the finished
    cycle on Friday morning, after Thursday's reports are in). The bounds are
    a plain date range - weekend days inside it only contribute if a report
    was actually submitted, since the ledger never synthesizes rows."""
    friday = reference_date - timedelta(days=(reference_date.weekday() - 4) % 7)
    thursday = friday + timedelta(days=6)
    return friday, thursday


def get_daily_benchmark_ledger(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Live (never stored) daily benchmark ledger for NUMERIC sub-activities:
    one row per (date, employee, sub_activity) the employee *actually
    submitted* this cycle (Fri..Thu). daily_target is a flat benchmark_value
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
        WorkReportPeriod,
        WorkReportStatus,
        WorkReportTask,
    )

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)

    actual_expr = actual_count_expr()
    hours_expr = func.coalesce(WorkReportTask.minutes_spent, 0) + func.coalesce(
        WorkReportTask.task_minutes_spent, 0
    )

    stmt = (
        select(
            DailyWorkReport.employee_id,
            DailyWorkReport.report_date,
            DailyWorkReport.day_status,
            WorkReportTask.period_id,
            WorkReportPeriod.work_fraction,
            # The employee's own DAY remark for this report date. Distinct from
            # ActivityMaster.benchmark_remarks (guidance TO the employee) — the
            # export's DAY REMARKS column carries only this one.
            DailyWorkReport.remarks.label("day_remarks"),
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
        # Period fraction (split-day, migration 0060). Outer join: rows written
        # by pre-period code have no period and fall back to the legacy
        # report-wide half_day rule below.
        .outerjoin(WorkReportPeriod, WorkReportTask.period_id == WorkReportPeriod.id)
        .where(
            DailyWorkReport.status == WorkReportStatus.submitted,
            DailyWorkReport.report_date >= week_start,
            DailyWorkReport.report_date <= week_end,
            # Pure per-day production only: legacy NUMERIC + NUMERIC_DAILY.
            # TASK_WITH_QUANTITY is deliberately EXCLUDED even though it carries
            # a quantity — it reaches the export via get_cycle_task_activities
            # instead, which renders a counted lumpsum's target/actual/pending
            # while keeping its completion/carry-forward. Including it here too
            # would list the same work twice and double-count the cycle.
            ActivityMaster.benchmark_type.in_(DAILY_QUANTITY_BENCHMARK_TYPES),
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
                # halve the day's target on a legacy (period-less) half day.
                "day_status": r.day_status,
                # Distinct period fractions this sub-activity spans that day —
                # the target scales by their sum (capped at a full day), so the
                # same activity in both halves reads ONE full-day target while
                # a single half reads half of it. Keyed per period so two rows
                # in the same period never double the target.
                "fractions": {},
                # Also per-report, not per-task: every detail row of this date
                # repeats it, so a filtered row still reads on its own.
                "day_remarks": r.day_remarks,
            },
        )
        bucket["actual"] += Decimal(r.actual or 0)
        bucket["hours_minutes"] += int(r.hours_minutes or 0)
        if r.period_id is not None and r.work_fraction is not None:
            bucket["fractions"][r.period_id] = Decimal(r.work_fraction)
        else:
            bucket["fractions"]["legacy"] = (
                Decimal("0.5") if r.day_status == DayStatus.half_day else Decimal("1.0")
            )
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
        base = Decimal(str(m["benchmark_value"] or 0))
        # Period-fraction scaling (split-day): target = base x the summed
        # distinct period fractions, capped at a full day. A legacy half_day
        # report contributes a single 0.5 "legacy" fraction — identical to the
        # old report-wide halving.
        fraction = min(
            Decimal("1.0"),
            sum(bucket["fractions"].values(), Decimal("0")) or Decimal("1.0"),
        )
        target = base * fraction
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
            "day_remarks": bucket["day_remarks"],
            "project_name": project_name,
            "project_code": project_code,
            "hours_minutes": bucket["hours_minutes"],
            "target": target,
            "actual": actual,
            "pending": pending,
        })
    out.sort(key=lambda r: (r["date"], r["sub_activity_name"]))
    return out


# Export display labels for a task row's reporting period. HALF DAY (LEGACY)
# covers every half-worked day whose worked half was never recorded — the
# backfilled/new legacy half_day reports — and is deliberately never resolved
# to FIRST/SECOND HALF by guessing.
DAY_PART_LABEL_FULL_DAY = "FULL DAY"
DAY_PART_LABEL_FIRST_HALF = "FIRST HALF"
DAY_PART_LABEL_SECOND_HALF = "SECOND HALF"
DAY_PART_LABEL_LEGACY_HALF_DAY = "HALF DAY (LEGACY)"
# Fixed display order of the parts within one date. FIRST HALF always precedes
# SECOND HALF; the full-day forms sort ahead of both.
DAY_PART_SORT_RANK = {
    DAY_PART_LABEL_FULL_DAY: 0,
    DAY_PART_LABEL_LEGACY_HALF_DAY: 1,
    DAY_PART_LABEL_FIRST_HALF: 2,
    DAY_PART_LABEL_SECOND_HALF: 3,
}
DAY_PART_HALF_LABELS = frozenset(
    {DAY_PART_LABEL_FIRST_HALF, DAY_PART_LABEL_SECOND_HALF}
)


def export_day_part_label(day_part, is_legacy_half_day, day_status) -> str:
    """DAY PART cell for one work-report-task row of the benchmark export.

    Derived ONLY from the task's linked period (day_part + is_legacy_half_day)
    — never from row order, activity order, or position in the report. A
    period-less deploy-gap row falls back to the report-wide legacy rule the
    read paths already use: a half_day header is a half-worked day whose
    worked half is unknown, anything else reads as a full day."""
    from app.modules.work_reports.models import DayPart, DayStatus

    if day_part is None:
        if day_status == DayStatus.half_day:
            return DAY_PART_LABEL_LEGACY_HALF_DAY
        return DAY_PART_LABEL_FULL_DAY
    if is_legacy_half_day:
        return DAY_PART_LABEL_LEGACY_HALF_DAY
    if day_part == DayPart.first_half.value:
        return DAY_PART_LABEL_FIRST_HALF
    if day_part == DayPart.second_half.value:
        return DAY_PART_LABEL_SECOND_HALF
    return DAY_PART_LABEL_FULL_DAY


def get_period_benchmark_ledger(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Per-PERIOD daily benchmark rows for the Pending Benchmark export: one
    row per (employee, date, DAY PART, sub_activity) actually submitted this
    cycle. Same row universe as get_daily_benchmark_ledger (which stays as-is
    for the live alert/performance views), with three deliberate differences:

    - A Split-Day date yields separate FIRST HALF / SECOND HALF rows instead
      of one merged row, each labelled via export_day_part_label.
    - target is the FROZEN submit-time benchmark_value_snapshot — the
      effective per-period target the submission already computed (base x
      fraction). No fraction is ever applied on top of it, and a later
      Activity Master edit never rewrites it. Only a pre-snapshot row falls
      back to the live value scaled by its period fraction (the old rule).
    - day_remarks carries the value the REMARKS column must show for the row:
      the row's own period remarks for a half, the report-header remark for
      Full-Day and legacy half-day rows. Never both, never the other half's.

    actual reads the count field named by relevant_count_field_snapshot
    (fallback: the live relevant_count_field), summed exactly as entered —
    never divided for half-day rows. Multiple task rows of one sub-activity
    inside ONE period (e.g. split across projects) still collapse to a single
    row: actuals sum, the effective target counts once, project labels join."""
    from app.modules.work_reports.models import (
        DailyWorkReport,
        DayStatus,
        WorkReportPeriod,
        WorkReportStatus,
        WorkReportTask,
    )

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)

    stmt = (
        select(
            DailyWorkReport.employee_id,
            DailyWorkReport.report_date,
            DailyWorkReport.day_status,
            DailyWorkReport.remarks.label("header_remarks"),
            WorkReportTask.period_id,
            WorkReportPeriod.day_part,
            WorkReportPeriod.is_legacy_half_day,
            WorkReportPeriod.remarks.label("period_remarks"),
            WorkReportPeriod.work_fraction,
            ActivityMaster.parent_id.label("activity_id"),
            ActivityMaster.id.label("sub_activity_id"),
            ActivityMaster.name.label("sub_activity_name"),
            ActivityMaster.benchmark_value,
            ActivityMaster.relevant_count_field,
            WorkReportTask.benchmark_value_snapshot,
            WorkReportTask.relevant_count_field_snapshot,
            WorkReportTask.tags_count,
            WorkReportTask.docs_count,
            WorkReportTask.bom_count,
            WorkReportTask.spares_count,
            WorkReportTask.pages_count,
            WorkReportTask.records_count,
            WorkReportTask.project_name,
            WorkReportTask.project_code,
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .outerjoin(WorkReportPeriod, WorkReportTask.period_id == WorkReportPeriod.id)
        .where(
            DailyWorkReport.status == WorkReportStatus.submitted,
            DailyWorkReport.report_date >= week_start,
            DailyWorkReport.report_date <= week_end,
            # Same disjoint split as the daily ledger: TASK_WITH_QUANTITY is
            # exported through get_cycle_task_activities only.
            ActivityMaster.benchmark_type.in_(DAILY_QUANTITY_BENCHMARK_TYPES),
        )
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(DailyWorkReport.employee_id.in_(employee_ids))

    rows = db.execute(stmt).all()
    if not rows:
        return []

    # One bucket per (employee, date, sub_activity, period). Period-less
    # deploy-gap rows of one report share a single "legacy" bucket, exactly as
    # the read-path fallback treats them (one full-day/legacy-half period).
    buckets: dict[tuple, dict] = {}
    for r in rows:
        key = (r.employee_id, r.report_date, r.sub_activity_id, r.period_id or "legacy")
        label = export_day_part_label(r.day_part, r.is_legacy_half_day, r.day_status)
        bucket = buckets.setdefault(
            key,
            {
                "employee_id": r.employee_id,
                "date": r.report_date,
                "activity_id": r.activity_id,
                "sub_activity_id": r.sub_activity_id,
                "sub_activity_name": r.sub_activity_name,
                "day_part": label,
                # The approved remarks mapping: a half shows its own period
                # remarks; FULL DAY / HALF DAY (LEGACY) show the header remark.
                "day_remarks": (
                    r.period_remarks
                    if label in DAY_PART_HALF_LABELS
                    else r.header_remarks
                ),
                "unit": None,
                "target_snapshot": None,
                # Fallback derivation for pre-snapshot rows only.
                "live_value": r.benchmark_value,
                "fraction": (
                    Decimal(str(r.work_fraction))
                    if r.work_fraction is not None
                    else (
                        Decimal("0.5")
                        if r.day_status == DayStatus.half_day
                        else Decimal("1.0")
                    )
                ),
                "actual": Decimal("0"),
                "projects": [],
                "project_codes": [],
            },
        )
        unit = r.relevant_count_field_snapshot or r.relevant_count_field
        if bucket["unit"] is None:
            bucket["unit"] = unit
        # The effective per-period target is frozen identically on every task
        # row of this period + sub-activity; take the first one, never sum.
        if bucket["target_snapshot"] is None and r.benchmark_value_snapshot is not None:
            bucket["target_snapshot"] = Decimal(str(r.benchmark_value_snapshot))
        count_column = COUNT_FIELD_BY_UNIT.get(unit)
        if count_column is not None:
            bucket["actual"] += Decimal(getattr(r, count_column) or 0)
        if r.project_name and r.project_name not in bucket["projects"]:
            bucket["projects"].append(r.project_name)
        if r.project_code and r.project_code not in bucket["project_codes"]:
            bucket["project_codes"].append(r.project_code)

    activity_ids = {b["activity_id"] for b in buckets.values() if b["activity_id"]}
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
    for bucket in buckets.values():
        if bucket["target_snapshot"] is not None:
            target = bucket["target_snapshot"]
        else:
            target = Decimal(str(bucket["live_value"] or 0)) * bucket["fraction"]
        actual = bucket["actual"]
        out.append({
            "employee_id": bucket["employee_id"],
            "date": bucket["date"],
            "activity_id": bucket["activity_id"],
            "activity_name": activity_names.get(bucket["activity_id"]),
            "sub_activity_id": bucket["sub_activity_id"],
            "sub_activity_name": bucket["sub_activity_name"],
            "benchmark_unit": bucket["unit"],
            "day_part": bucket["day_part"],
            "day_remarks": bucket["day_remarks"],
            "project_name": ", ".join(bucket["projects"]) or None,
            "project_code": ", ".join(bucket["project_codes"]) or None,
            "target": target,
            "actual": actual,
            "pending": max(Decimal("0"), target - actual),
        })
    out.sort(
        key=lambda r: (
            r["date"],
            r["sub_activity_name"] or "",
            DAY_PART_SORT_RANK.get(r["day_part"], 0),
        )
    )
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

    Scoped to the CURRENT cycle (Fri..Thu) like the benchmark ledger: only
    tasks whose due_date falls in this cycle (week_start <= due_date < today)
    count, so overdue resets every Friday alongside the numeric benchmark
    backlog rather than carrying stale deadlines forward indefinitely.

    Besides the alert-view fields, each row carries the sub-activity's
    benchmark metadata (benchmark_value / benchmark_period_days /
    benchmark_unit) and the task's counted `actual` — additive extras for the
    pending-benchmark export's lumpsum rows; the Pydantic alert schemas
    ignore them."""
    from app.modules.work_reports.models import DailyWorkReport, WorkItem, WorkReportTask

    today = today or date.today()
    week_start, _ = compute_week_bounds(today)
    # Completion is authoritative on the work item (approved design §12): once its
    # completed_on is set, EVERY daily row of the item counts as done -- including
    # an earlier row whose mirrored is_completed flag is stale because the task was
    # finished on a later continuation. Legacy (work_item_id NULL) rows fall back
    # to the row's own is_completed.
    completed_flag = case(
        (WorkReportTask.work_item_id.is_not(None), WorkItem.completed_on.is_not(None)),
        else_=WorkReportTask.is_completed,
    )

    actual_expr = actual_count_expr()

    stmt = (
        select(
            DailyWorkReport.employee_id,
            WorkReportTask.id.label("work_report_task_id"),
            WorkReportTask.work_item_id,
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.project_code,
            WorkReportTask.project_name,
            DailyWorkReport.report_date,
            WorkReportTask.due_date,
            ActivityMaster.benchmark_value,
            ActivityMaster.benchmark_period_days,
            ActivityMaster.relevant_count_field,
            actual_expr.label("actual"),
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .outerjoin(WorkItem, WorkReportTask.work_item_id == WorkItem.id)
        .where(
            ActivityMaster.benchmark_type.in_(TASK_BENCHMARK_TYPES),
            WorkReportTask.due_date.is_not(None),
            WorkReportTask.due_date >= week_start,
            WorkReportTask.due_date < today,
            completed_flag.is_(False),
        )
    )
    if employee_ids is not None:
        if not employee_ids:
            return []
        stmt = stmt.where(DailyWorkReport.employee_id.in_(employee_ids))

    rows = db.execute(stmt).all()
    out: list[dict] = []
    # A work item spans several daily rows sharing one frozen due_date; collapse
    # them to ONE overdue result, summing the counted actual and keeping the
    # earliest entry date. Legacy (work_item_id NULL) rows stay 1:1.
    by_item: dict[uuid.UUID, dict] = {}
    for r in rows:
        _, days_overdue = compute_overdue(r.due_date, False, today)
        if r.work_item_id is not None and r.work_item_id in by_item:
            agg = by_item[r.work_item_id]
            agg["actual"] = (agg["actual"] or 0) + (r.actual or 0)
            agg["report_date"] = min(agg["report_date"], r.report_date)
            continue
        entry = {
            "employee_id": r.employee_id,
            "work_report_task_id": r.work_report_task_id,
            "work_item_id": r.work_item_id,
            "activity_name": r.activity_name,
            "sub_activity_name": r.sub_activity_name,
            "project_code": r.project_code,
            "project_name": r.project_name,
            "report_date": r.report_date,
            "due_date": r.due_date,
            "days_overdue": days_overdue,
            "benchmark_value": r.benchmark_value,
            "benchmark_period_days": r.benchmark_period_days,
            "benchmark_unit": r.relevant_count_field,
            "actual": r.actual,
        }
        if r.work_item_id is not None:
            by_item[r.work_item_id] = entry
        out.append(entry)
    return out


def get_cycle_task_activities(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Every TASK_BASED (lumpsum) work-report-task whose due_date falls inside
    the cycle (week_start <= due_date <= week_end, Fri..Thu) -- completed AND
    still-open alike. This is the full-context source for the pending-benchmark
    export: unlike get_overdue_activities (open + past-due only), a lumpsum a
    person actually finished this cycle appears too, so the sheet shows why an
    over-100% achiever looks the way they do rather than hiding their wins.

    Each row carries the same benchmark metadata + counted `actual` as
    get_overdue_activities, plus `is_completed` and `days_overdue` (0 when
    completed or not yet past due), so the export can render a Completed /
    Overdue / Pending cell trio without a second query. `day_part` labels the
    row's reporting period (export_day_part_label — Day Part only attaches to
    the row, deadlines are never scaled by it) and `period_remarks` carries
    that period's own remark for the export's REMARKS mapping."""
    from app.modules.work_reports.models import (
        DailyWorkReport,
        WorkItem,
        WorkReportPeriod,
        WorkReportTask,
    )

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)
    # Authoritative completion from the work item (see get_overdue_activities).
    completed_flag = case(
        (WorkReportTask.work_item_id.is_not(None), WorkItem.completed_on.is_not(None)),
        else_=WorkReportTask.is_completed,
    )

    actual_expr = actual_count_expr()

    stmt = (
        select(
            DailyWorkReport.employee_id,
            WorkReportTask.id.label("work_report_task_id"),
            WorkReportTask.work_item_id,
            WorkReportTask.sub_activity_id,
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.project_code,
            WorkReportTask.project_name,
            DailyWorkReport.report_date,
            DailyWorkReport.day_status,
            # See the ledger query: the employee's DAY remark, never the
            # Activity Master benchmark guidance.
            DailyWorkReport.remarks.label("day_remarks"),
            WorkReportPeriod.day_part.label("period_day_part"),
            WorkReportPeriod.is_legacy_half_day,
            WorkReportPeriod.remarks.label("period_remarks"),
            WorkReportTask.due_date,
            completed_flag.label("is_completed"),
            ActivityMaster.benchmark_value,
            ActivityMaster.benchmark_period_days,
            ActivityMaster.relevant_count_field,
            actual_expr.label("actual"),
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .outerjoin(WorkItem, WorkReportTask.work_item_id == WorkItem.id)
        .outerjoin(WorkReportPeriod, WorkReportTask.period_id == WorkReportPeriod.id)
        .where(
            ActivityMaster.benchmark_type.in_(TASK_BENCHMARK_TYPES),
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
    out: list[dict] = []
    # One result per work item (its daily entries share a frozen due_date and
    # completion): sum the counted actual across entries, keep the earliest date.
    # Legacy (work_item_id NULL) rows remain one result per row.
    by_item: dict[uuid.UUID, dict] = {}
    for r in rows:
        _, days_overdue = compute_overdue(r.due_date, r.is_completed, today)
        if r.work_item_id is not None and r.work_item_id in by_item:
            agg = by_item[r.work_item_id]
            agg["actual"] = (agg["actual"] or 0) + (r.actual or 0)
            agg["report_date"] = min(agg["report_date"], r.report_date)
            continue
        entry = {
            "employee_id": r.employee_id,
            "work_report_task_id": r.work_report_task_id,
            "work_item_id": r.work_item_id,
            "sub_activity_id": r.sub_activity_id,
            "activity_name": r.activity_name,
            "sub_activity_name": r.sub_activity_name,
            "project_code": r.project_code,
            "project_name": r.project_name,
            "report_date": r.report_date,
            "day_remarks": r.day_remarks,
            "day_part": export_day_part_label(
                r.period_day_part, r.is_legacy_half_day, r.day_status
            ),
            "period_remarks": r.period_remarks,
            "due_date": r.due_date,
            "is_completed": r.is_completed,
            "days_overdue": days_overdue,
            "benchmark_value": r.benchmark_value,
            "benchmark_period_days": r.benchmark_period_days,
            "benchmark_unit": r.relevant_count_field,
            "actual": r.actual,
        }
        if r.work_item_id is not None:
            by_item[r.work_item_id] = entry
        out.append(entry)
    return out


def get_task_status_activities(
    db: Session,
    *,
    employee_ids: set[uuid.UUID] | None = None,
    today: date | None = None,
) -> list[dict]:
    """Live (never stored) list of TASK_BASED rows for the Homepage Alerts
    'Pending Tasks (This Week)' panel: every task whose due_date falls inside
    the current cycle (week_start <= due_date <= week_end, Fri..Thu), completed
    or not. The employee dashboard is deliberately current-cycle-only — a task
    from a previous cycle (whether still pending or long overdue) never appears
    here, even though its row stays in the database. The view resets every
    Friday with the week bounds.

    `status` is "completed" once the task is marked done (so a within-week task
    finished later in the week reads as Completed), otherwise "pending" — we no
    longer surface a separate "due today" state, since the panel is scoped to
    the week rather than to overdue-only rows. `days_overdue` is kept for the
    schema but only non-zero for an uncompleted task already past its due_date
    within this same week (not displayed on the employee card)."""
    from app.modules.work_reports.models import DailyWorkReport, WorkItem, WorkReportTask

    today = today or date.today()
    week_start, week_end = compute_week_bounds(today)
    # Authoritative completion from the work item (see get_overdue_activities).
    completed_flag = case(
        (WorkReportTask.work_item_id.is_not(None), WorkItem.completed_on.is_not(None)),
        else_=WorkReportTask.is_completed,
    )

    hours_expr = func.coalesce(WorkReportTask.minutes_spent, 0) + func.coalesce(
        WorkReportTask.task_minutes_spent, 0
    )

    stmt = (
        select(
            DailyWorkReport.employee_id,
            WorkReportTask.id.label("work_report_task_id"),
            WorkReportTask.work_item_id,
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.project_name,
            WorkReportTask.project_code,
            DailyWorkReport.report_date,
            WorkReportTask.due_date,
            func.coalesce(WorkItem.completed_on, WorkReportTask.completed_date).label(
                "completed_date"
            ),
            completed_flag.label("is_completed"),
            hours_expr.label("hours_minutes"),
        )
        .join(DailyWorkReport, WorkReportTask.report_id == DailyWorkReport.id)
        .join(ActivityMaster, WorkReportTask.sub_activity_id == ActivityMaster.id)
        .outerjoin(WorkItem, WorkReportTask.work_item_id == WorkItem.id)
        .where(
            ActivityMaster.benchmark_type.in_(TASK_BENCHMARK_TYPES),
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
    out: list[dict] = []
    # One row per work item (entries share a frozen due_date + completion): sum
    # the time spent across daily entries, keep the earliest date. Legacy
    # (work_item_id NULL) rows remain one result per row.
    by_item: dict[uuid.UUID, dict] = {}
    for r in rows:
        overdue = not r.is_completed and r.due_date < today
        if r.work_item_id is not None and r.work_item_id in by_item:
            agg = by_item[r.work_item_id]
            agg["hours_minutes"] += int(r.hours_minutes or 0)
            agg["report_date"] = min(agg["report_date"], r.report_date)
            continue
        entry = {
            "employee_id": r.employee_id,
            "work_report_task_id": r.work_report_task_id,
            "work_item_id": r.work_item_id,
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
        }
        if r.work_item_id is not None:
            by_item[r.work_item_id] = entry
        out.append(entry)
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


def list_all_sub_activities_flat(
    db: Session,
    *,
    active_only: bool = True,
    employee_id: uuid.UUID | None = None,
) -> list[dict]:
    """Every leaf row across every Activity, joined to the parent's name — the
    shape the work-report cascading select ultimately needs.

    When `employee_id` is given (the report-dropdown case), RESTRICTED activities
    are filtered in-DB: a sub-activity only appears if its parent Activity is
    COMMON, or the employee has an active grant on it. Passing None (the admin
    reference case) returns every sub-activity regardless of access."""
    from app.modules.activity_master.access_service import usable_activity_clause

    Parent = aliased(ActivityMaster)
    stmt = (
        select(ActivityMaster, Parent.name)
        .join(Parent, ActivityMaster.parent_id == Parent.id)
        .where(ActivityMaster.level == LEVEL_SUB_ACTIVITY)
    )
    if employee_id is not None:
        # EXISTS-based restricted filter (indexed, no N+1). Applied only for the
        # employee-scoped dropdown; the admin list keeps every row.
        stmt = stmt.where(usable_activity_clause(Parent, employee_id))
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
            # The master's own guidance + unit note. Without these the report
            # form cannot render the configured benchmark guidance panel.
            "benchmark_unit_note": sub.benchmark_unit_note,
            "benchmark_remarks": sub.benchmark_remarks,
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
    if new_type in QUANTITY_BENCHMARK_TYPES:
        if new_value is None:
            raise AppError(
                "validation_error",
                f"benchmark_value is required when benchmark_type is {new_type}.",
                422,
            )
        if new_count_field is None:
            raise AppError(
                "validation_error",
                f"relevant_count_field is required when benchmark_type is {new_type} "
                f"(it's the benchmark's actual-value source).",
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
