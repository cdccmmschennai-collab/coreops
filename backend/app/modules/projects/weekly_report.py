"""Project Weekly Report (Phase 7) — the ONE authoritative dataset behind both
the browser preview and the Excel download.

What this report is:

  Every piece of work reported against ONE project during ONE Friday-Thursday
  cycle, one row per work-report activity line, for the project's assigned Head.

What it is deliberately NOT:

  It is not the Tag Scope / Summary view. Those two answer "how far through the
  project's estimated tag universe is each tag-counted sub-activity", and so are
  restricted to ``relevant_count_field == 'tags'``. This report answers "what did
  my team actually do this week", so it carries EVERY activity line on the
  project: tag-counted, docs/BOM/spares/pages/records-counted, task-mode and
  activities with no benchmark configuration at all (PROJECT MEETING, TRAINING).
  Nothing is filtered on unit, benchmark type or count value.

Row granularity
  One row per ``work_report_tasks`` row — i.e. per employee + date + work period
  + activity line. Two different activities the same person reported in the same
  half-day stay two rows; they are separate work entries and merging them would
  destroy the counts.

Which reports count (report lifecycle)
  Every NON-DRAFT report: submitted, granted (reopened for edit) and the two
  legacy statuses rejected / approved. Excluded: draft.

  A draft is private to its author until filed — the Head cannot see another
  employee's draft anywhere else in CoreOps (see work_reports.service._apply_scope,
  where PM scope is literally "all non-draft"), and a formal operational report
  they can export and circulate must not be the one place it leaks. This is
  deliberately NOT the tag-scope consumption rule: tag_progress counts drafts
  because an in-progress draft is a real claim on scarce scope capacity. Reserving
  capacity and reporting finished work are different questions.

Where the numbers come from
  Benchmark  -> ``work_report_tasks.benchmark_value_snapshot`` — the effective
                target frozen at submit time (base x day-part fraction), never a
                fresh calculation from the current Activity Master. A benchmark
                edited after the fact must not rewrite what somebody was measured
                against last week.
  Counts     -> the six count columns on the same row, unchanged.
  Task state -> the same derived lifecycle the rest of the app shows
                (work_items.lifecycle_of over the row's frozen due date), never a
                stored status column.
  Remarks    -> the note attached to this row: its own activity remark, else its
                own period's. Never the Query / Issues field. See _remarks.

Nothing here writes, and nothing here changes a benchmark, a tag scope or a
report. It is a pure read.
"""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import case, select
from sqlalchemy.orm import Session, aliased

from app.modules.activity_master.models import (
    ActivityMaster,
    BENCHMARK_TYPE_TASK_WITH_QUANTITY,
    COUNT_FIELDS,
    COUNT_FIELD_BY_UNIT,
    QUANTITY_BENCHMARK_TYPES,
    TASK_BENCHMARK_TYPES,
)
from app.modules.activity_master.service import compute_week_bounds
from app.modules.employees.models import Employee
from app.modules.projects.models import Project
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayPart,
    WorkReportPeriod,
    WorkReportStatus,
    WorkReportTask,
)
from app.modules.work_reports.work_items import lifecycle_of

# The report's business day. Cycle boundaries are a business fact, so the "which
# week is current" question is answered in the company's timezone rather than in
# whatever timezone the server happens to run in — at 00:30 IST on a Friday the
# new cycle has already started, even though UTC still says Thursday.
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")

# The only two selectable cycles in this phase, as offsets back from the cycle
# containing today. No arbitrary date range: the Head picks a week, not a span.
CYCLE_OFFSETS: dict[str, int] = {"current": 0, "previous": 1}

# Report statuses included. Everything except `draft` — see the module docstring.
EXCLUDED_STATUSES = frozenset({WorkReportStatus.draft})

# Work Period — the project allocation of the reported day. Deliberately NOT
# "Day Status": day_status is the attendance-shaped taxonomy (Leave, Week Off,
# Company Holiday, Work at Office...), a different question entirely.
WORK_PERIOD_FULL_DAY = "full_day"
WORK_PERIOD_FIRST_HALF = "first_half"
WORK_PERIOD_SECOND_HALF = "second_half"
# Periods backfilled from historical day_status='half_day' reports: half a day
# was worked but WHICH half was never recorded, so it is reported as its own
# value rather than guessed into First or Second. Same distinction the benchmark
# export already draws with its "HALF DAY (LEGACY)" cell.
WORK_PERIOD_LEGACY_HALF = "legacy_half_day"

WORK_PERIOD_LABELS: dict[str, str] = {
    WORK_PERIOD_FULL_DAY: "Full Day",
    WORK_PERIOD_FIRST_HALF: "First Half",
    WORK_PERIOD_SECOND_HALF: "Second Half",
    WORK_PERIOD_LEGACY_HALF: "Half Day (Legacy)",
}

# Task lifecycle labels, mirroring the existing work-report UI map
# (features/work-reports/components/period-activity-editor.tsx LIFECYCLE_LABEL)
# so one task never reads "Completed" on the report form and something else in
# the Head's export. No new task-status vocabulary is invented here.
TASK_STATUS_LABELS: dict[str, str] = {
    "IN_PROGRESS": "In progress",
    "DUE_TODAY": "Due today",
    "OVERDUE": "Overdue",
    "COMPLETED_ON_TIME": "Completed",
    "COMPLETED_LATE": "Completed late",
}

# The Benchmark cell for a completion-only task activity. The existing term from
# the Benchmark Guide (features/benchmark-guide/format.ts), not a new one.
#
# There is deliberately no blank-cell placeholder here: this service emits null
# for "does not apply", and each client renders its own "-" (the workbook's
# _WR_BLANK, the tab's VALUE_NOT_APPLICABLE). A null never becomes a 0.
LUMP_SUM_LABEL = "Lump Sum"


def business_today() -> date:
    """Today in the company's business timezone (see BUSINESS_TZ)."""
    return datetime.now(BUSINESS_TZ).date()


def resolve_cycle(cycle: str | None, *, today: date | None = None) -> tuple[str, date, date]:
    """(cycle, start, end) for "current" or "previous".

    The Friday-Thursday bounds come from ``compute_week_bounds`` — the same
    helper the benchmark cycle, the task-continuation window and the PM exports
    all use, so a Head's "this week" is exactly the company's benchmark week.

    Raises ValueError for anything other than the two accepted values, rather
    than falling back to a cycle nobody asked for.
    """
    key = (cycle or "current").strip().lower()
    if key not in CYCLE_OFFSETS:
        raise ValueError(
            f"cycle must be one of {sorted(CYCLE_OFFSETS)}, got {cycle!r}"
        )
    start, _ = compute_week_bounds(today or business_today())
    start -= timedelta(days=7 * CYCLE_OFFSETS[key])
    # A cycle is always exactly seven calendar days, Friday..Thursday.
    return key, start, start + timedelta(days=6)


def _work_period(period: WorkReportPeriod | None) -> str:
    """The row's Work Period value.

    A NULL period is a legacy row written before migration 0060; the whole
    report was a full day then, which is how every other read path treats it.
    """
    if period is None:
        return WORK_PERIOD_FULL_DAY
    if period.day_part == DayPart.full_day.value:
        return WORK_PERIOD_LEGACY_HALF if period.is_legacy_half_day else WORK_PERIOD_FULL_DAY
    if period.day_part == DayPart.first_half.value:
        return WORK_PERIOD_FIRST_HALF
    if period.day_part == DayPart.second_half.value:
        return WORK_PERIOD_SECOND_HALF
    return WORK_PERIOD_FULL_DAY


def _benchmark_type(task: WorkReportTask, sub: ActivityMaster | None) -> str | None:
    """The benchmark mode this row was reported under.

    The frozen snapshot wins: it is what the row was actually evaluated against.
    The live master value is only a fallback for rows saved before the snapshot
    column existed.
    """
    return task.benchmark_type_snapshot or (sub.benchmark_type if sub else None)


def _benchmark(task: WorkReportTask, sub: ActivityMaster | None) -> tuple[float | None, str | None]:
    """(numeric benchmark, textual benchmark) for the Benchmark column.

    Exactly one of the two is set, or neither:
      * a quantity mode with a frozen target -> the number (a real number, so the
        Excel cell stays numeric and sortable),
      * a completion-only task              -> "Lump Sum",
      * anything else                       -> neither, and the clients render "-".

    A non-benchmark activity (PROJECT MEETING, TRAINING) lands in the third case
    and still gets its row: the work happened.
    """
    btype = _benchmark_type(task, sub)
    value = task.benchmark_value_snapshot
    if btype is None:
        return None, None
    if btype in QUANTITY_BENCHMARK_TYPES and value is not None:
        return float(value), None
    if btype in TASK_BENCHMARK_TYPES and btype != BENCHMARK_TYPE_TASK_WITH_QUANTITY:
        return None, LUMP_SUM_LABEL
    return None, None


def _counts(task: WorkReportTask, sub: ActivityMaster | None) -> dict[str, int | None]:
    """The six unit columns, with "not applicable" kept distinct from "zero".

    The columns are NOT NULL DEFAULT 0 in the database, so an untouched unit and
    a genuinely-reported zero look identical there. A unit is reported here when
    it either carries a value, or is the unit this row's benchmark reads its
    actual from — so a tag row that legitimately completed 0 tags still shows 0
    under TAGS, while its DOCS/BOM/SPARES stay blank instead of printing four
    meaningless zeroes.

    Deliberately not exclusive: if a row carries both tags and docs, both are
    reported. This is a detailed report, and no validation guarantees only one
    unit per row.
    """
    unit = task.relevant_count_field_snapshot or (
        sub.relevant_count_field if sub else None
    )
    out: dict[str, int | None] = {}
    for field in COUNT_FIELDS:
        value = getattr(task, COUNT_FIELD_BY_UNIT[field], 0) or 0
        out[field] = int(value) if (value or field == unit) else None
    return out


def _remarks(
    task: WorkReportTask, report: DailyWorkReport, period: WorkReportPeriod | None
) -> str | None:
    """The Remarks cell: the note that belongs to THIS row, most specific first.

    CoreOps stores three remark-shaped things, and only two of them describe the
    work on a line:

      work_report_tasks.description  the per-activity note (rendered as
                                     "Remarks" on the report detail page). Most
                                     specific, so it wins when present. In
                                     practice the current report form does not
                                     collect it, which is exactly why it cannot
                                     be the only source.
      the row's OWN period remark    a half's own note for a First/Second Half
                                     row; the header note for a Full Day. This
                                     is the same definition the benchmark export
                                     already uses for its REMARKS column, so one
                                     row reads the same in both workbooks.
      daily_work_reports.query_text  DELIBERATELY EXCLUDED. Query / Issues is a
                                     question for the PM, not a description of
                                     the work, and merging it would make the
                                     column mean two different things.

    A half-day row never falls back to the header note: the header belongs to
    the whole day, and attributing it to one half would put words about the
    morning against the afternoon's activity.
    """
    own = (task.description or "").strip()
    if own:
        return own
    if period is not None and period.day_part in (
        DayPart.first_half.value,
        DayPart.second_half.value,
    ):
        return (period.remarks or "").strip() or None
    # Full Day (and legacy rows with no period): the period's own note if the
    # split-day form wrote one, else the report header's note.
    period_note = (period.remarks or "").strip() if period is not None else ""
    return period_note or (report.remarks or "").strip() or None


def _task_status(
    task: WorkReportTask, sub: ActivityMaster | None, today: date
) -> tuple[str | None, str | None]:
    """(lifecycle value, label) for a task-mode row, else (None, None).

    Derived — never read from a stored status column, which does not exist — via
    the same ``lifecycle_of`` the open-task list and the report form use. A task
    row with no due date (legacy, pre-migration-0056) reports no status rather
    than a guessed one.
    """
    btype = _benchmark_type(task, sub)
    if btype is None or btype not in TASK_BENCHMARK_TYPES:
        return None, None
    if task.due_date is None:
        return None, None
    completed_on = task.completed_date if task.is_completed else None
    if task.is_completed and completed_on is None:
        # Completion flagged without a stamped date (should not happen; be
        # explicit rather than silently reporting the task as still running).
        completed_on = task.due_date
    value = lifecycle_of(task.due_date, completed_on, today=today).value
    return value, TASK_STATUS_LABELS.get(value, value)


def build_rows(
    db: Session, project: Project, start: date, end: date, *, today: date | None = None
) -> list[dict]:
    """Every non-draft activity line reported on this project between the two
    dates, normalised into report rows.

    Ordering (identical for the preview and the export, because there is only
    one list): date ascending, then Work Period in business order (Full Day,
    First Half, Second Half), then employee name, then activity / sub-activity,
    and finally the row id so equal rows never swap places between two calls.

    Project isolation is structural: the WHERE filters on project_id first, so a
    split day whose other half belongs to another project contributes exactly
    one row here — its own half — and nothing of the other project's leaks in.
    """
    today = today or business_today()
    sub = aliased(ActivityMaster)      # the reported sub-activity
    parent = aliased(ActivityMaster)   # its parent Activity

    part_rank = case(
        (WorkReportPeriod.day_part == DayPart.first_half.value, 1),
        (WorkReportPeriod.day_part == DayPart.second_half.value, 2),
        else_=0,
    )
    stmt = (
        select(WorkReportTask, DailyWorkReport, Employee, WorkReportPeriod, sub, parent)
        .join(DailyWorkReport, DailyWorkReport.id == WorkReportTask.report_id)
        .join(Employee, Employee.id == DailyWorkReport.employee_id)
        .outerjoin(WorkReportPeriod, WorkReportPeriod.id == WorkReportTask.period_id)
        .outerjoin(sub, sub.id == WorkReportTask.sub_activity_id)
        .outerjoin(parent, parent.id == sub.parent_id)
        .where(
            WorkReportTask.project_id == project.id,
            DailyWorkReport.report_date >= start,
            DailyWorkReport.report_date <= end,
            DailyWorkReport.status.not_in(EXCLUDED_STATUSES),
        )
        .order_by(
            DailyWorkReport.report_date,
            part_rank,
            Employee.first_name,
            Employee.last_name,
            WorkReportTask.activity_name,
            WorkReportTask.sub_activity_name,
            WorkReportTask.id,
        )
    )

    rows: list[dict] = []
    for task, report, employee, period, sub_row, parent_row in db.execute(stmt).all():
        period_value = _work_period(period)
        benchmark, benchmark_label = _benchmark(task, sub_row)
        status_value, status_label = _task_status(task, sub_row, today)
        rows.append(
            {
                "report_date": report.report_date,
                "work_period": period_value,
                "work_period_label": WORK_PERIOD_LABELS[period_value],
                "employee_name": employee.full_name,
                # Project CODE only, from the canonical project row — never the
                # project name, and never parsed out of a display string.
                "project_code": project.code,
                # Snapshots frozen at save time, so a later Activity Master
                # rename never rewrites history. The live master is a fallback
                # for rows that predate the snapshot columns.
                "activity_name": task.activity_name
                or (parent_row.name if parent_row else None),
                "sub_activity_name": task.sub_activity_name
                or (sub_row.name if sub_row else None),
                "benchmark": benchmark,
                "benchmark_label": benchmark_label,
                **_counts(task, sub_row),
                "task_status": status_value,
                "task_status_label": status_label,
                # The note belonging to THIS row: its own activity remark when
                # there is one, else its own period's. Never the Query / Issues
                # field — see _remarks.
                "remarks": _remarks(task, report, period),
            }
        )
    return rows


def get_project_weekly_report(
    db: Session, project: Project, cycle: str | None, *, today: date | None = None
) -> dict:
    """The whole payload: cycle metadata, the project's code, and the rows.

    The single dataset builder. The preview endpoint serialises this; the Excel
    endpoint renders this same dict into a workbook. There is no second query
    and no second calculation, which is what guarantees the Head can never see
    25 rows on screen and 27 in the file.

    Authorization is the caller's job (see projects.service) — this function is
    pure data.
    """
    key, start, end = resolve_cycle(cycle, today=today)
    rows = build_rows(db, project, start, end, today=today)
    return {
        "project_id": project.id,
        "project_code": project.code,
        "period": {"type": key, "start_date": start, "end_date": end},
        "rows": rows,
        "row_count": len(rows),
    }


def _code_prefix(project_code: str | None) -> str:
    """The project's leading number - "4460-GC22104900" -> "4460".

    Only the digits at the FRONT of the code, capped at four: that is the part
    the business names a project by. "" when the code is missing or does not
    start with a number, which is the case the filename drops the prefix for
    entirely rather than inventing one.
    """
    digits = ""
    for char in (project_code or "").strip():
        if not char.isdigit():
            break
        digits += char
        if len(digits) == 4:
            break
    return digits


def _range_label(start: date, end: date) -> str:
    """`7 AUG - 13 AUG` - day unpadded, month uppercase."""
    return f"{start.day} {start.strftime('%b').upper()} - {end.day} {end.strftime('%b').upper()}"


def export_filename(project_code: str | None, start: date, end: date) -> str:
    """`4460 WEEKLY REPORT [7 AUG - 13 AUG].xlsx`.

    The project's leading number only - never its code in full and never its
    name. A project with no code (or one that does not start with a number)
    drops the prefix: `WEEKLY REPORT [7 AUG - 13 AUG].xlsx`, with no stray
    leading space.

    Quotes, slashes and control characters are stripped so a code cannot break
    the Content-Disposition header; the spaces and brackets are deliberate and
    are legal inside a quoted filename.
    """
    prefix = _code_prefix(project_code)
    name = f"{prefix} WEEKLY REPORT [{_range_label(start, end)}].xlsx".lstrip()
    return "".join(c for c in name if c.isprintable() and c not in '"\\/:*?<>|')

