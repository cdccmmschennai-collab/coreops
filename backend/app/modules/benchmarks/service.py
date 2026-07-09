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
    compute_week_bounds,
    get_daily_benchmark_ledger,
    get_overdue_activities,
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


def get_employees_performance(
    db: Session,
    *,
    page: int = 1,
    page_size: int = 10,
    search: str = "",
    sort: str = "productivity",
    order: str = "asc",
    cycle: str = "current",
    today: date | None = None,
) -> dict:
    """Layer 1 comparison list. Lists ALL active employees (a no-activity
    employee shows zeros / 'no_data', not absent — this is a management
    roster). Reuses the frozen _employee_comparison rollup for employees with
    benchmark activity this cycle; everyone else is filled with zeros.

    `cycle` selects the Fri..Thu window ("current" default for viewing;
    "previous" lets a PM review the finished cycle) — same live recompute as
    the pending export, no persistence."""
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


def _cycle_window(cycle: str, today: date) -> tuple[date, date]:
    """Fri..Thu bounds of the requested cycle: "current" contains today,
    "previous" is the last completed one."""
    cycle_start, cycle_end = compute_week_bounds(today)
    if cycle == "previous":
        cycle_start -= timedelta(days=7)
        cycle_end -= timedelta(days=7)
    return cycle_start, cycle_end


def _project_label(code: str | None, name: str | None) -> str:
    """PROJECT CODE & TITLE cell: "<code> - <title>", falling back to
    whichever half exists."""
    if code and name:
        return f"{code} - {name}"
    return code or name or ""


def _fmt_qty(value: Decimal) -> str:
    """Trim trailing zeros for display inside text cells (1000.00 -> 1000)."""
    return f"{value.normalize():f}"


def _task_export_cells(r: dict) -> dict:
    """Cell values for one TASK_BASED (lumpsum) overdue row of the export.

    CASE A — count-based lumpsum (benchmark_value + a counted unit): text
    cells like "1000 TAGS PER DAY" / "500 TAGS" / "500 TAGS", with the bare
    numbers contributed to the employee TOTAL row.

    CASE B — plain finish-by-due-date task: "FINISH WITHIN A DAY" /
    "NOT COMPLETED" / "N DAYS OVERDUE", contributing nothing to totals."""
    period = r["benchmark_period_days"] or 1
    unit = r["benchmark_unit"]
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
            "pending": f"{_fmt_qty(pending)} {unit_label}",
            "target_total": target,
            "actual_total": actual,
            "pending_total": pending,
        }
    days = r["days_overdue"]
    return {
        # No counted unit to place this under — default to the TAGS column.
        "unit": unit or "tags",
        "target": "FINISH WITHIN A DAY" if period == 1 else f"FINISH WITHIN {period} DAYS",
        "actual": "NOT COMPLETED",
        "pending": f"{days} DAY{'S' if days != 1 else ''} OVERDUE",
        "target_total": None,
        "actual_total": None,
        "pending_total": None,
    }


def get_pending_benchmark_export(
    db: Session, *, cycle: str = "previous", today: date | None = None
) -> dict:
    """Rows for the PM's pending-benchmark XLSX export. Reuses the frozen
    ledger and the same reconciliation the dashboard shows: only NUMERIC rows
    whose *reconciled* pending is still > 0 are exported (a day recovered by a
    later day's surplus is excluded), so the sheet never disagrees with the
    team-alerts backlog. TASK_BASED (lumpsum) rows come from the same frozen
    get_overdue_activities the alert views use — incomplete tasks past their
    due date within the cycle (see _task_export_cells for their cell text);
    the two sources are disjoint by benchmark_type, so nothing duplicates.
    An employee with nothing pending in either source doesn't appear at all.

    `cycle` picks the Fri..Thu window: "current" is the cycle containing
    today; "previous" (the default) is the last completed one — PMs export on
    Friday morning after Thursday's reports are in. Nothing is persisted; the
    previous cycle is recomputed live from the same work-report rows."""
    cycle_start, cycle_end = _cycle_window(cycle, today or date.today())

    # The ledger derives its own bounds from `today`, so any date inside the
    # wanted cycle selects it; use its end day.
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=cycle_end)
    effective = _reconcile_effective_pending(daily)
    overdue = get_overdue_activities(db, employee_ids=None, today=cycle_end)

    pending_rows = []
    for r in daily:
        remaining = effective.get(
            (r["employee_id"], r["date"], r["sub_activity_id"]), r["pending"]
        )
        if remaining > 0:
            pending_rows.append({**r, "pending": remaining})

    labels: dict[uuid.UUID, str] = {}
    employee_ids = (
        {r["employee_id"] for r in pending_rows}
        | {r["employee_id"] for r in overdue}
    )
    if employee_ids:
        emps = db.execute(
            select(Employee).where(Employee.id.in_(employee_ids))
        ).scalars().all()
        labels = {e.id: f"{e.employee_code} - {e.full_name}" for e in emps}

    # Each row's target/actual/pending are the CELL values (Decimal or text);
    # the *_total twins are what the employee TOTAL row sums (None = excluded,
    # e.g. CASE B text rows).
    rows = [
        {
            "employee_label": labels.get(r["employee_id"], "-"),
            "date": r["date"],
            "project": _project_label(r["project_code"], r["project_name"]),
            "activity": r["activity_name"] or "",
            "sub_activity": r["sub_activity_name"],
            "unit": r["benchmark_unit"],
            "target": r["target"],
            "actual": r["actual"],
            "pending": r["pending"],
            "target_total": r["target"],
            "actual_total": r["actual"],
            "pending_total": r["pending"],
        }
        for r in pending_rows
    ]
    rows += [
        {
            "employee_label": labels.get(r["employee_id"], "-"),
            "date": r["report_date"],
            "project": _project_label(r["project_code"], r["project_name"]),
            "activity": r["activity_name"] or "",
            "sub_activity": r["sub_activity_name"],
            **_task_export_cells(r),
        }
        for r in overdue
    ]
    # Employee-wise sections, date-wise within each — the workbook builder
    # groups on contiguous employee_label runs.
    rows.sort(key=lambda r: (r["employee_label"], r["date"], r["sub_activity"]))
    return {"rows": rows, "cycle_start": cycle_start, "cycle_end": cycle_end}


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
