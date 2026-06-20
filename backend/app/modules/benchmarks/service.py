"""Homepage Alerts service — shapes the live Phase 1 daily benchmark ledger
(activity_master.service) into the two read-only views the spec calls for:
an employee's own "My Alerts" and a PM's org-wide "Team" view.

No notifications, no persistence, no scheduled jobs — every value here is
recomputed from scratch on each call."""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.activity_master.service import (
    get_daily_benchmark_ledger,
    get_overdue_activities,
    get_task_status_activities,
)
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.users.models import User


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


def _employee_comparison(daily: list[dict], names: dict[uuid.UUID, str]) -> list[dict]:
    """Per-employee weekly benchmark rollup for the PM 'compare employee
    performance' table: each employee's summed target/actual/pending across
    every NUMERIC sub-activity day this week, plus a productivity % using the
    same weighted total-actual/total-target formula as the org KPI, scoped to
    one employee (NOT a change to the frozen calculation — just grouped by
    employee). Lowest productivity sorts first so a PM sees who needs
    attention; employees with no benchmark target (no NUMERIC work this week)
    have productivity_pct = None and sort last."""
    agg: dict[uuid.UUID, dict] = {}
    for r in daily:
        a = agg.setdefault(
            r["employee_id"],
            {"target": Decimal("0"), "actual": Decimal("0"), "pending": Decimal("0")},
        )
        a["target"] += r["target"]
        a["actual"] += r["actual"]
        a["pending"] += r["pending"]

    rows = []
    for emp_id, a in agg.items():
        pct = (a["actual"] / a["target"] * 100) if a["target"] > 0 else None
        rows.append({
            "employee_id": emp_id,
            "employee_name": names.get(emp_id, "—"),
            "target": a["target"],
            "actual": a["actual"],
            "pending": a["pending"],
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
    today: date | None = None,
) -> dict:
    """Layer 1 comparison list. Lists ALL active employees (a no-activity
    employee shows zeros / 'no_data', not absent — this is a management
    roster). Reuses the frozen _employee_comparison rollup for employees with
    benchmark activity this week; everyone else is filled with zeros."""
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=today)

    emps = db.execute(
        select(Employee).where(
            Employee.status == EmployeeStatus.active, Employee.deleted_at.is_(None)
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

    hours = sum(r["hours_minutes"] for r in daily)
    pending = sum(1 for r in daily if r["pending"] > 0)
    completed = sum(1 for r in daily if r["target"] > 0 and r["actual"] >= r["target"])

    return {
        "employee_id": employee_id,
        "employee_name": name,
        "productivity_pct": _aggregate_productivity(daily),
        "hours_this_week_minutes": hours,
        "completed_benchmarks": completed,
        "pending_benchmarks": pending,
        "overdue_activities": len(overdue),
    }


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


def get_team_alerts(db: Session, actor: User, *, today: date | None = None) -> dict:
    """project_manager only — org-wide, no employee_ids filter."""
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=today)
    shortfalls = [_daily_row(r) for r in daily if r["pending"] > 0]
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

    backlog = [
        {**r, "employee_name": names.get(r["employee_id"], "—")} for r in shortfalls
    ]
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
