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


def get_team_alerts(db: Session, actor: User, *, today: date | None = None) -> dict:
    """project_manager only — org-wide, no employee_ids filter."""
    daily = get_daily_benchmark_ledger(db, employee_ids=None, today=today)
    shortfalls = [_daily_row(r) for r in daily if r["pending"] > 0]
    overdue = get_overdue_activities(db, employee_ids=None, today=today)

    employee_ids = {r["employee_id"] for r in shortfalls} | {r["employee_id"] for r in overdue}
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
        "backlog": backlog,
        "overdue": overdue_rows,
        "kpis": {
            "total_employees": len(total_employees),
            "weekly_productivity_pct": _aggregate_productivity(daily),
            "total_pending_benchmarks": len(backlog),
            "total_overdue_activities": len(overdue_rows),
        },
    }
