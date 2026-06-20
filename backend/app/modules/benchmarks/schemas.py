"""Homepage Alerts schemas — read-only data structures over the live Phase 1
benchmark engine (activity_master.service.get_daily_benchmark_ledger /
get_overdue_activities). No persistence here: every field is computed fresh
on each request."""
import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class DailyBenchmarkRowOut(BaseModel):
    """One row of 'My Alerts' / 'Team Benchmark Backlog' — a single day's
    actual/target/pending for one NUMERIC sub-activity, with pending > 0
    (a clean day doesn't show up in this list, though it still counts
    toward the weekly productivity %). `sub_activity_name` is the "Activity
    Name" shown in the UI examples (e.g. "FMTL Rework")."""

    date: date
    sub_activity_id: uuid.UUID
    activity_name: str | None
    sub_activity_name: str
    project_name: str | None
    project_code: str | None
    hours_minutes: int
    actual: Decimal
    target: Decimal
    pending: Decimal
    benchmark_unit: str | None


class OverdueActivityOut(BaseModel):
    """One row of 'My Alerts' / 'Team Overdue Activities' — a TASK_BASED
    work-report-task row past its due_date and not completed."""

    work_report_task_id: uuid.UUID
    activity_name: str | None
    sub_activity_name: str
    due_date: date
    days_overdue: int


class TaskStatusOut(BaseModel):
    """One row of 'My Alerts' / 'Overdue Tasks' panel — a TASK_BASED
    work-report-task row, broader than OverdueActivityOut: also covers
    due-today and rows completed this week, with `status` driving the
    Pending/Due Today/Completed badge in the UI."""

    work_report_task_id: uuid.UUID
    activity_name: str | None
    sub_activity_name: str
    project_name: str | None
    project_code: str | None
    report_date: date
    due_date: date
    completed_date: date | None
    hours_minutes: int
    status: str
    days_overdue: int


class MyAlertsSummaryOut(BaseModel):
    pending_benchmarks_count: int
    overdue_activities_count: int
    productivity_pct: Decimal | None


class MyAlertsOut(BaseModel):
    shortfalls: list[DailyBenchmarkRowOut]
    daily: list[DailyBenchmarkRowOut]
    overdue: list[OverdueActivityOut]
    tasks: list[TaskStatusOut]
    summary: MyAlertsSummaryOut


class TeamBacklogRowOut(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    date: date
    activity_name: str | None
    sub_activity_name: str
    actual: Decimal
    target: Decimal
    pending: Decimal
    benchmark_unit: str | None


class TeamOverdueRowOut(BaseModel):
    employee_id: uuid.UUID
    employee_name: str
    activity_name: str | None
    sub_activity_name: str
    due_date: date
    days_overdue: int


class TeamComparisonRowOut(BaseModel):
    """One row of the PM 'compare employee performance' table — an employee's
    weekly benchmark rollup (summed target/actual/pending + productivity %).
    productivity_pct is None when the employee logged no NUMERIC benchmark
    work this week (no target to measure against)."""

    employee_id: uuid.UUID
    employee_name: str
    target: Decimal
    actual: Decimal
    pending: Decimal
    productivity_pct: Decimal | None


class TeamKpisOut(BaseModel):
    total_employees: int
    weekly_productivity_pct: Decimal | None
    total_pending_benchmarks: int
    total_overdue_activities: int


class TeamAlertsOut(BaseModel):
    comparison: list[TeamComparisonRowOut]
    backlog: list[TeamBacklogRowOut]
    overdue: list[TeamOverdueRowOut]
    kpis: TeamKpisOut


# ── PM employee-performance system (Layer 1 table + Layer 2/3 overview) ─────────


class EmployeePerformanceRowOut(BaseModel):
    """One row of the PM comparison table (Layer 1). Comparison columns ONLY —
    inspection/overview fields deliberately live on EmployeeOverviewOut so the
    table can't grow into an analytics surface. `productivity` is None when the
    employee logged no NUMERIC benchmark work this week; `status` is derived
    from it via the frozen thresholds in service._status_from_pct."""

    id: uuid.UUID
    name: str
    employee_code: str
    target: Decimal
    actual: Decimal
    pending: Decimal
    productivity: Decimal | None
    status: str  # on_track | at_risk | behind | no_data


class EmployeesPerformancePageOut(BaseModel):
    items: list[EmployeePerformanceRowOut]
    total: int
    page: int
    page_size: int


class EmployeeOverviewOut(BaseModel):
    """Shared payload for Layer 2 (drawer) + Layer 3 (Overview tab). Single
    source so the two surfaces can never diverge."""

    employee_id: uuid.UUID
    employee_name: str
    productivity_pct: Decimal | None
    hours_this_week_minutes: int
    completed_benchmarks: int
    pending_benchmarks: int
    overdue_activities: int


class EmployeeBenchmarksOut(BaseModel):
    """One employee's FULL weekly daily ledger (every NUMERIC sub-activity day,
    not just the pending ones) + overdue, so the client can run the same
    backlog reconciliation the employee's own widget does — later-day surplus
    paying down earlier deficits. Raw per-day pending lives in `daily`;
    reconciliation is applied client-side (display only)."""

    daily: list[DailyBenchmarkRowOut]
    overdue: list[OverdueActivityOut]
