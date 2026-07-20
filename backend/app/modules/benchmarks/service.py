"""Homepage Alerts service — shapes the live Phase 1 daily benchmark ledger
(activity_master.service) into the two read-only views the spec calls for:
an employee's own "My Alerts" and a PM's org-wide "Team" view.

No notifications, no persistence, no scheduled jobs — every value here is
recomputed from scratch on each call."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.modules.activity_master.service import (
    DAY_PART_HALF_LABELS,
    DAY_PART_SORT_RANK,
    compute_week_bounds,
    get_cycle_task_activities,
    get_daily_benchmark_ledger,
    get_overdue_activities,
    get_period_benchmark_ledger,
    get_task_status_activities,
)
from app.modules.attendance.models import AttendanceRecord, AttendanceStatus
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.users.models import User, UserRole

# Managerial roles never author work reports, so they have no benchmark data —
# they're excluded from the employee benchmark-tracking roster entirely.
_NON_AUTHORING_ROLES = (UserRole.project_manager, UserRole.manager)


def _daily_row(r: dict) -> dict:
    """Reshape a get_daily_benchmark_ledger() row to the
    DailyBenchmarkRowOut/TeamBacklogRowOut shape — same field names, this
    just exists as a single seam in case the two ever need to diverge."""
    return {
        "employee_id": r["employee_id"],
        "date": r["date"],
        "sub_activity_id": r["sub_activity_id"],
        "activity_name": r["activity_name"],
        "sub_activity_name": r["sub_activity_name"],
        "project_name": r["project_name"],
        "project_code": r["project_code"],
        "hours_minutes": r["hours_minutes"],
        "actual": r["actual"],
        "target": r["target"],
        "pending": r["pending"],
        "benchmark_unit": r["benchmark_unit"],
    }


def _aggregate_productivity(rows: list[dict]) -> Decimal | None:
    """Org/employee-wide productivity = total actual / total target, summed
    across every elapsed day (not a plain average of per-row percentages,
    so a 10-unit day and a 1000-unit day don't count equally). Summing the
    daily rows here is equivalent to summing weekly rows the old engine
    produced — same formula, just fed from daily granularity now."""
    total_target = sum((r["target"] for r in rows), Decimal("0"))
    total_actual = sum((r["actual"] for r in rows), Decimal("0"))
    if total_target <= 0:
        return None
    return (total_actual / total_target) * 100


def get_my_alerts(db: Session, actor: User, *, today: date | None = None) -> dict:
    me = _current_employee(db, actor)
    if me is None:
        return {
            "shortfalls": [],
            "daily": [],
            "overdue": [],
            "tasks": [],
            "summary": {
                "pending_benchmarks_count": 0,
                "overdue_activities_count": 0,
                "productivity_pct": None,
            },
        }

    daily = get_daily_benchmark_ledger(db, employee_ids={me.id}, today=today)
    shortfalls = [_daily_row(r) for r in daily if r["pending"] > 0]
    overdue = get_overdue_activities(db, employee_ids={me.id}, today=today)
    tasks = get_task_status_activities(db, employee_ids={me.id}, today=today)

    return {
        "shortfalls": shortfalls,
        "daily": [_daily_row(r) for r in daily],
        "overdue": overdue,
        "tasks": tasks,
        "summary": {
            "pending_benchmarks_count": len(shortfalls),
            "overdue_activities_count": len(overdue),
            "productivity_pct": _aggregate_productivity(daily),
        },
    }


def _reconcile_effective_pending(daily: list[dict]) -> dict[tuple, Decimal]:
    """Per-row *effective* benchmark pending after backlog recovery, keyed by
    (employee_id, date, sub_activity_id). Mirrors the frontend
    reconciliation.ts: within each (employee, sub_activity), days are walked in
    date order and a later day's surplus pays down earlier outstanding deficits
    (oldest first); leftover surplus is dropped, never carried forward to a
    future day. The ledger already keys one row per (employee, date,
    sub_activity), so these keys are unique. The per-day productivity math
    (actual/target) is intentionally left untouched."""
    by_sub: dict[tuple[uuid.UUID, uuid.UUID], list[dict]] = {}
    for r in daily:
        by_sub.setdefault((r["employee_id"], r["sub_activity_id"]), []).append(r)

    effective: dict[tuple, Decimal] = {}
    for rows in by_sub.values():
        ordered = sorted(rows, key=lambda r: r["date"])
        outstanding: list[list] = []  # [row_key, remaining_deficit], oldest first
        for row in ordered:
            target = Decimal(str(row["target"]))
            actual = Decimal(str(row["actual"]))
            deficit = max(Decimal("0"), target - actual)
            surplus = max(Decimal("0"), actual - target)
            key = (row["employee_id"], row["date"], row["sub_activity_id"])
            effective[key] = deficit
            while surplus > 0 and outstanding:
                head = outstanding[0]
                applied = min(surplus, head[1])
                head[1] -= applied
                surplus -= applied
                effective[head[0]] -= applied
                if head[1] <= 0:
                    outstanding.pop(0)
            if deficit > 0:
                outstanding.append([key, deficit])
    return effective


def _reconciled_pending_by_employee(daily: list[dict]) -> dict[uuid.UUID, Decimal]:
    """Each employee's summed *reconciled* benchmark pending (see
    _reconcile_effective_pending), so the comparison table agrees with the
    per-employee detail view."""
    by_emp: dict[uuid.UUID, Decimal] = {}
    for (emp_id, _d, _s), pending in _reconcile_effective_pending(daily).items():
        by_emp[emp_id] = by_emp.get(emp_id, Decimal("0")) + pending
    return by_emp


def _employee_comparison(daily: list[dict], names: dict[uuid.UUID, str]) -> list[dict]:
    """Per-employee weekly benchmark rollup for the PM 'compare employee
    performance' table: each employee's summed target/actual across every
    NUMERIC sub-activity day this week, plus a productivity % using the same
    weighted total-actual/total-target formula as the org KPI, scoped to one
    employee. `pending` is the *reconciled* backlog (later-day surplus clears
    earlier deficits) so this table matches the detail view. Lowest
    productivity sorts first so a PM sees who needs attention; employees with
    no benchmark target (no NUMERIC work this week) have productivity_pct =
    None and sort last."""
    reconciled = _reconciled_pending_by_employee(daily)
    agg: dict[uuid.UUID, dict] = {}
    for r in daily:
        a = agg.setdefault(
            r["employee_id"],
            {"target": Decimal("0"), "actual": Decimal("0")},
        )
        a["target"] += r["target"]
        a["actual"] += r["actual"]

    rows = []
    for emp_id, a in agg.items():
        pct = (a["actual"] / a["target"] * 100) if a["target"] > 0 else None
        rows.append({
            "employee_id": emp_id,
            "employee_name": names.get(emp_id, "—"),
            "target": a["target"],
            "actual": a["actual"],
            "pending": reconciled.get(emp_id, Decimal("0")),
            "productivity_pct": pct,
        })
    rows.sort(
        key=lambda r: (
            r["productivity_pct"] is None,
            r["productivity_pct"] if r["productivity_pct"] is not None else Decimal("0"),
            r["employee_name"],
        )
    )
    return rows


def _status_from_pct(pct: Decimal | None) -> str:
    """Frozen thresholds — MUST match the frontend pctVariant() used in the
    benchmark comparison: >=100 met, >=70 near-miss, else shortfall; None means
    no benchmark target this week (no NUMERIC work) and is NOT counted as a
    shortfall."""
    if pct is None:
        return "no_data"
    if pct >= 100:
        return "on_track"
    if pct >= 70:
        return "at_risk"
    return "behind"


_PERF_SORTABLE = {"productivity", "pending", "actual", "target", "name"}
_PERF_STATUS = {"all", "needs_review", "on_track"}


def get_employees_performance(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 10,
    search: str = "",
    status: str = "all",
    sort: str = "productivity",
    order: str = "asc",
    cycle: str | int | None = 0,
    today: date | None = None,
) -> dict:
    """Layer 1 comparison list. Lists ALL active employees (a no-activity
    employee shows zeros / 'no_data', not absent — this is a management
    roster). Reuses the frozen _employee_comparison rollup for employees with
    benchmark activity this cycle; everyone else is filled with zeros.

    `cycle` selects the Fri..Thu window as an offset back from today's cycle
    (0 = current, up to MAX_WEEK_OFFSET); "current"/"previous" still resolve to
    0 and 1. Same live recompute as the pending export, through the same
    _cycle_window, so table and export always agree."""
    _, cycle_end = _cycle_window(cycle, today or date.today())
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=cycle_end)

    emps = db.execute(
        select(Employee)
        .outerjoin(User, Employee.user_id == User.id)
        .where(
            Employee.status == EmployeeStatus.active,
            Employee.deleted_at.is_(None),
            # Keep report-authoring staff (and any without a login); drop PMs/managers.
            or_(User.id.is_(None), User.role.notin_(_NON_AUTHORING_ROLES)),
        )
    ).scalars().all()
    names = {e.id: e.full_name for e in emps}

    rollup = {r["employee_id"]: r for r in _employee_comparison(daily, names)}

    rows: list[dict] = []
    for e in emps:
        r = rollup.get(e.id)
        pct = r["productivity_pct"] if r else None
        rows.append({
            "id": e.id,
            "name": e.full_name,
            "employee_code": e.employee_code,
            "target": r["target"] if r else Decimal("0"),
            "actual": r["actual"] if r else Decimal("0"),
            "pending": r["pending"] if r else Decimal("0"),
            "productivity": pct,
            "status": _status_from_pct(pct),
        })

    if search:
        q = search.lower()
        rows = [
            r for r in rows
            if q in r["name"].lower() or q in r["employee_code"].lower()
        ]

    # Status filter — the same rule the frontend Status badge uses: any pending
    # backlog → "Needs Review", zero → "On Track". Applied BEFORE sort/paginate
    # so `total` and the page slice both reflect the filtered set (a filter that
    # matches one employee must report total 1, not the full roster count).
    if status not in _PERF_STATUS:
        status = "all"
    if status == "needs_review":
        rows = [r for r in rows if r["pending"] > 0]
    elif status == "on_track":
        rows = [r for r in rows if r["pending"] <= 0]

    if sort not in _PERF_SORTABLE:
        sort = "productivity"
    reverse = order == "desc"
    if sort == "name":
        rows.sort(key=lambda r: r["name"].lower(), reverse=reverse)
    elif sort == "productivity":
        # None always sorts last (no data is not the worst performer).
        rows.sort(
            key=lambda r: (
                r["productivity"] is None,
                r["productivity"] if r["productivity"] is not None else Decimal("0"),
                r["name"].lower(),
            ),
            reverse=reverse,
        )
    else:
        rows.sort(key=lambda r: r[sort], reverse=reverse)

    total = len(rows)
    start = max(0, (page - 1) * page_size)
    return {
        "items": rows[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_employee_overview(
    db: Session, employee_id: uuid.UUID, *, today: date | None = None
) -> dict:
    """Shared Layer 2/3 overview for one employee — same frozen ledger, scoped
    to a single employee. completed_benchmarks counts days where a target
    existed and was met (actual >= target); pending_benchmarks counts days
    still short."""
    emp = db.get(Employee, employee_id)
    name = emp.full_name if emp else "—"

    daily = get_daily_benchmark_ledger(db, employee_ids={employee_id}, today=today)
    overdue = get_overdue_activities(db, employee_ids={employee_id}, today=today)

    days_worked = _days_worked_this_week(db, employee_id, today=today)
    pending = sum(1 for r in daily if r["pending"] > 0)
    completed = sum(1 for r in daily if r["target"] > 0 and r["actual"] >= r["target"])

    return {
        "employee_id": employee_id,
        "employee_name": name,
        "productivity_pct": _aggregate_productivity(daily),
        "days_worked_this_week": days_worked,
        "completed_benchmarks": completed,
        "pending_benchmarks": pending,
        "overdue_activities": len(overdue),
    }


def _days_worked_this_week(
    db: Session, employee_id: uuid.UUID, *, today: date | None = None
) -> int:
    """Count distinct days this cycle (Fri..Thu) the employee actually worked,
    i.e. has a present/half_day attendance record. Mirrors the Fri..Thu cycle
    used by the benchmark ledger so "this week" means the same thing across the
    overview."""
    week_start, week_end = compute_week_bounds(today or date.today())
    return db.execute(
        select(func.count(func.distinct(AttendanceRecord.attendance_date))).where(
            AttendanceRecord.employee_id == employee_id,
            AttendanceRecord.status.in_(
                (AttendanceStatus.present, AttendanceStatus.half_day)
            ),
            AttendanceRecord.attendance_date >= week_start,
            AttendanceRecord.attendance_date <= week_end,
        )
    ).scalar_one()


def get_employee_benchmarks(
    db: Session, employee_id: uuid.UUID, *, today: date | None = None
) -> dict:
    """PM-only per-employee weekly ledger for the detail page's Benchmarks tab.
    Returns the FULL daily ledger (not just pending rows) so the client can
    reconcile backlog the same way the employee's own widget does — a day short
    100 that a later day's surplus recovers should read ~0, not 100."""
    daily = get_daily_benchmark_ledger(db, employee_ids={employee_id}, today=today)
    overdue = get_overdue_activities(db, employee_ids={employee_id}, today=today)
    return {
        "daily": [_daily_row(r) for r in daily],
        "overdue": overdue,
    }


MAX_WEEK_OFFSET = 3
# Legacy string cycle values, kept working as aliases. The integer offset is the
# single source of truth — these only translate into it.
_CYCLE_ALIASES = {"current": 0, "previous": 1}


def resolve_week_offset(cycle: str | int | None) -> int:
    """The one place a cycle selector becomes an integer offset.

    Accepts the integer offsets 0..3 (0 = the cycle containing today, N = N
    cycles back) and the two legacy aliases "current" (0) and "previous" (1).
    Anything else — a negative offset, an offset past MAX_WEEK_OFFSET, or an
    unknown string — raises ValueError rather than silently falling back to a
    different cycle, which would hand back data for a period nobody asked for."""
    if cycle is None:
        return 0
    if isinstance(cycle, bool):
        raise ValueError(f"invalid cycle: {cycle!r}")
    if isinstance(cycle, int):
        offset = cycle
    else:
        text = str(cycle).strip().lower()
        if text in _CYCLE_ALIASES:
            return _CYCLE_ALIASES[text]
        try:
            offset = int(text)
        except ValueError:
            raise ValueError(f"invalid cycle: {cycle!r}") from None
    if not 0 <= offset <= MAX_WEEK_OFFSET:
        raise ValueError(
            f"week_offset must be an integer from 0 to {MAX_WEEK_OFFSET}, got {offset}"
        )
    return offset


def _cycle_window(cycle: str | int | None, today: date) -> tuple[date, date]:
    """Fri..Thu bounds of the requested cycle, `week_offset` cycles back from
    the one containing `today`. Offset 0 is the current cycle, 1 the previous,
    up to MAX_WEEK_OFFSET. Every caller (table data AND export) resolves through
    here, so the selector can never disagree between the two."""
    offset = resolve_week_offset(cycle)
    cycle_start, _ = compute_week_bounds(today)
    cycle_start -= timedelta(days=7 * offset)
    # A cycle is always exactly 7 calendar days, Friday..Thursday.
    return cycle_start, cycle_start + timedelta(days=6)


def _day_remarks(value: str | None) -> str:
    """DAY REMARKS cell: the employee's own remark for that report date, or ""
    when unset or whitespace-only. Never Activity Master's benchmark_remarks —
    that is guidance TO the employee and belongs nowhere in this column."""
    return (value or "").strip()


def _project_label(code: str | None, name: str | None) -> str:
    """PROJECT CODE & TITLE cell: "<code> - <title>", falling back to
    whichever half exists."""
    if code and name:
        return f"{code} - {name}"
    return code or name or ""


def _normalize_sub_activity_label(name: str | None) -> str:
    """Collapse internal whitespace and uppercase a sub-activity name, for the
    LEGACY fallback grouping key only (rows with no sub_activity_id)."""
    return " ".join((name or "").split()).upper()


def _sub_activity_group_key(sub_activity_id: uuid.UUID | None, sub_activity_name: str | None) -> str:
    """Primary per-sub-activity aggregation key for the full-cycle export. The
    export groups on employee + cycle + sub_activity; the cycle is constant for
    one export, so the varying part is the employee (grouped upstream) and this
    key. It uses the sub_activity_id so two sub-activities that merely share a
    similar displayed NAME never collapse into one total; a normalized label is
    used only as a fallback for legacy rows that predate the id."""
    if sub_activity_id is not None:
        return f"id:{sub_activity_id}"
    return f"name:{_normalize_sub_activity_label(sub_activity_name)}"


def _fmt_qty(value: Decimal) -> str:
    """Trim trailing zeros for display inside text cells (1000.00 -> 1000)."""
    return f"{value.normalize():f}"


def _task_pending_text(r: dict) -> str:
    """PENDING-cell text for a lumpsum row by its state: finished this cycle ->
    "NO PENDING"; still open and past due -> "N DAYS OVERDUE"; open but not yet
    due -> "PENDING"."""
    if r.get("is_completed"):
        return "NO PENDING"
    days = r["days_overdue"]
    if days > 0:
        return f"{days} DAY{'S' if days != 1 else ''} OVERDUE"
    return "PENDING"


def _task_export_cells(r: dict) -> dict:
    """Cell values for one TASK_BASED (lumpsum) row of the export. The row may
    be completed, overdue, or still-open (see get_cycle_task_activities).

    CASE A — count-based lumpsum (benchmark_value + a counted unit): text
    cells like "1000 TAGS PER DAY" / "500 TAGS" / "500 TAGS" (or "NO PENDING"
    when finished), with the bare numbers contributed to the employee TOTAL row
    and the achievement %.

    CASE B — plain finish-by-due-date task: "FINISH WITHIN A DAY" /
    "FINISHED"|"NOT COMPLETED" / "NO PENDING"|"N DAYS OVERDUE"|"PENDING",
    contributing nothing to the numeric totals."""
    period = r["benchmark_period_days"] or 1
    unit = r["benchmark_unit"]
    completed = bool(r.get("is_completed"))
    if r["benchmark_value"] is not None and unit:
        target = Decimal(str(r["benchmark_value"]))
        actual = Decimal(str(r["actual"] or 0))
        pending = max(Decimal("0"), target - actual)
        unit_label = unit.upper()
        per = "PER DAY" if period == 1 else f"PER {period} DAYS"
        return {
            "unit": unit,
            "target": f"{_fmt_qty(target)} {unit_label} {per}",
            "actual": f"{_fmt_qty(actual)} {unit_label}",
            "pending": "NO PENDING" if completed else f"{_fmt_qty(pending)} {unit_label}",
            "target_total": target,
            "actual_total": actual,
            "pending_total": pending,
        }
    return {
        # No counted unit to place this under — default to the TAGS column.
        "unit": unit or "tags",
        "target": "FINISH WITHIN A DAY" if period == 1 else f"FINISH WITHIN {period} DAYS",
        "actual": "FINISHED" if completed else "NOT COMPLETED",
        "pending": _task_pending_text(r),
        "target_total": None,
        "actual_total": None,
        "pending_total": None,
    }


def get_pending_benchmark_export(
    db: Session, *, cycle: str | int | None = 1, today: date | None = None
) -> dict:
    """Rows for the PM's full-cycle benchmark XLSX export.

    EVERY employee with ANY benchmark activity this cycle is exported — a daily
    quantity ledger day or a task lumpsum — regardless of whether anything is
    still pending. Management evaluates complete cycle performance, so an
    employee who met or exceeded every benchmark appears alongside one who fell
    short; nothing is filtered on pending > 0. Each employee shows their WHOLE
    Fri..Thu benchmark story: every daily-quantity day (over-, exactly-, or
    under-target) and every task lumpsum (completed, overdue, or still open).

    The two row sources are disjoint BY CONSTRUCTION, so nothing duplicates:
    the ledger selects DAILY_QUANTITY_BENCHMARK_TYPES (NUMERIC, NUMERIC_DAILY)
    while the lumpsum query selects TASK_BENCHMARK_TYPES (TASK_BASED,
    TASK_STATUS_ONLY, TASK_WITH_QUANTITY), and those two sets are defined as
    disjoint in activity_master/models.py. TASK_WITH_QUANTITY carries a quantity
    but is exported through the lumpsum side only — _task_row_cells CASE A gives
    it real target/actual/pending numbers, so it still participates in the
    numeric subtotal without being counted twice.

    Each NUMERIC detail row shows its own *daily* shortage (max(0, daily target
    - daily actual)); the per-employee TOTAL row instead nets the whole cycle
    per unit (see the workbook builder), so a day's overachievement compensates
    another day's shortfall within the same benchmark unit — the total pending
    is NOT the sum of the daily shortages.

    `cycle` picks the Fri..Thu window as an offset back from the one containing
    today (0 = current, 1 = previous, up to MAX_WEEK_OFFSET); the legacy
    "current"/"previous" strings still resolve to 0 and 1. The default is the
    last completed cycle — PMs export on Friday morning after Thursday's reports
    are in.

    Cycle isolation is structural, not filtered after the fact: both source
    queries derive their own Fri..Thu bounds from the `today` they are handed,
    so passing this cycle's end date makes them select exactly this cycle's
    rows. Nothing is persisted or cached; every cycle is recomputed live from
    the same work-report rows, so no neighbouring cycle can leak in."""
    cycle_start, cycle_end = _cycle_window(cycle, today or date.today())

    # The ledger derives its own bounds from `today`, so any date inside the
    # wanted cycle selects it; use its end day. The export reads the PER-PERIOD
    # ledger (frozen snapshots, one row per DAY PART) — the merged
    # get_daily_benchmark_ledger stays serving the live alert/performance views.
    daily = get_period_benchmark_ledger(db, employee_ids=None, today=cycle_end)
    cycle_tasks = get_cycle_task_activities(db, employee_ids=None, today=cycle_end)

    # Inclusion set: everyone with any benchmark activity this cycle, achievers
    # included. No pending filter.
    included = {r["employee_id"] for r in daily} | {r["employee_id"] for r in cycle_tasks}

    labels: dict[uuid.UUID, str] = {}
    if included:
        emps = db.execute(
            select(Employee).where(Employee.id.in_(included))
        ).scalars().all()
        labels = {e.id: f"{e.employee_code} - {e.full_name}" for e in emps}

    # Every NUMERIC day for an included employee, showing that day's own
    # shortage. The *_total twins feed the per-sub-activity SUB ACTIVITY TOTAL
    # row (netted across dates within one employee + sub-activity + unit).
    rows = [
        {
            "employee_label": labels.get(r["employee_id"], "-"),
            "date": r["date"],
            "day_part": r["day_part"],
            "project": _project_label(r["project_code"], r["project_name"]),
            "activity": r["activity_name"] or "",
            "sub_activity": r["sub_activity_name"],
            "sub_activity_id": r["sub_activity_id"],
            "group_key": _sub_activity_group_key(r["sub_activity_id"], r["sub_activity_name"]),
            "unit": r["benchmark_unit"],
            "target": r["target"],
            # Already mapped per the row's own period by the period ledger:
            # half rows carry that half's remarks, full-day/legacy rows the
            # report-header remark.
            "day_remarks": _day_remarks(r.get("day_remarks")),
            "actual": r["actual"],
            "pending": r["pending"],  # per-period shortage; the subtotal nets the cycle
            "target_total": r["target"],
            "actual_total": r["actual"],
            "pending_total": r["pending"],
        }
        for r in daily
        if r["employee_id"] in included
    ]
    # Every lumpsum (completed / overdue / open) for an included employee. The
    # REMARKS mapping matches the numeric rows: a task in a half shows that
    # half's period remarks, a full-day/legacy task the report-header remark.
    rows += [
        {
            "employee_label": labels.get(r["employee_id"], "-"),
            "date": r["report_date"],
            "day_part": r["day_part"],
            "project": _project_label(r["project_code"], r["project_name"]),
            "activity": r["activity_name"] or "",
            "sub_activity": r["sub_activity_name"],
            "sub_activity_id": r["sub_activity_id"],
            "group_key": _sub_activity_group_key(r["sub_activity_id"], r["sub_activity_name"]),
            "day_remarks": _day_remarks(
                r.get("period_remarks")
                if r["day_part"] in DAY_PART_HALF_LABELS
                else r.get("day_remarks")
            ),
            **_task_export_cells(r),
        }
        for r in cycle_tasks
        if r["employee_id"] in included
    ]

    # Sort so every row of one sub-activity stays contiguous before its SUB
    # ACTIVITY TOTAL: employee, then activity, then sub-activity name (the
    # required display order), then group_key (keeps two same-named-but-distinct
    # sub-activities apart), then date, then DAY PART (FIRST HALF always before
    # SECOND HALF — never DB insertion order), then project. ACHIEVEMENT % /
    # DIFFERENCE % are derived per SUB ACTIVITY TOTAL by the workbook builder
    # from the *_total twins, so they are not precomputed per employee here.
    rows.sort(
        key=lambda r: (
            r["employee_label"],
            r["activity"] or "",
            r["sub_activity"] or "",
            r["group_key"],
            r["date"],
            DAY_PART_SORT_RANK.get(r["day_part"], 0),
            r["project"],
        )
    )
    return {
        "rows": rows,
        "cycle_start": cycle_start,
        "cycle_end": cycle_end,
    }


def get_team_alerts(db: Session, actor: User, *, today: date | None = None) -> dict:
    """project_manager only — org-wide, no employee_ids filter."""
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=today)
    effective = _reconcile_effective_pending(daily)
    overdue = get_overdue_activities(db, employee_ids=None, today=today)

    # Names for everyone who appears in any view: the comparison table covers
    # every employee with benchmark activity this week (all of `daily`), not
    # just those currently in backlog/overdue.
    employee_ids = (
        {r["employee_id"] for r in daily}
        | {r["employee_id"] for r in overdue}
    )
    names: dict[uuid.UUID, str] = {}
    if employee_ids:
        emps = db.execute(select(Employee).where(Employee.id.in_(employee_ids))).scalars().all()
        names = {e.id: e.full_name for e in emps}

    total_employees = db.execute(
        select(Employee.id).where(
            Employee.status == EmployeeStatus.active, Employee.deleted_at.is_(None)
        )
    ).scalars().all()

    # Reconciled team backlog: only activities still incomplete after a later
    # day's surplus has paid down earlier deficits, with the reconciled
    # remaining quantity. Matches the comparison table and the detail view.
    backlog = []
    for r in daily:
        remaining = effective.get(
            (r["employee_id"], r["date"], r["sub_activity_id"]), r["pending"]
        )
        if remaining > 0:
            row = _daily_row(r)
            row["pending"] = remaining
            row["employee_name"] = names.get(r["employee_id"], "—")
            backlog.append(row)
    backlog.sort(key=lambda r: (r["employee_name"], r["date"]))
    overdue_rows = [
        {**r, "employee_name": names.get(r["employee_id"], "—")} for r in overdue
    ]

    return {
        "comparison": _employee_comparison(daily, names),
        "backlog": backlog,
        "overdue": overdue_rows,
        "kpis": {
            "total_employees": len(total_employees),
            "weekly_productivity_pct": _aggregate_productivity(daily),
            "total_pending_benchmarks": len(backlog),
            "total_overdue_activities": len(overdue_rows),
        },
    }
