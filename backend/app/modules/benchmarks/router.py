"""Homepage Alerts endpoints.

  GET /benchmarks/my-alerts     employee's own shortfalls/overdue/summary (any authenticated user)
  GET /benchmarks/team-alerts   org-wide backlog/overdue/KPIs (project_manager only)

These back the existing homepage — no new dashboard page, no notification
tab. Everything is computed live from Phase 1's get_daily_benchmark_ledger
/ get_overdue_activities; nothing here is persisted or scheduled.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.benchmarks import service
from app.modules.reports_export.export import (
    build_pending_benchmark_workbook,
    date_range_label,
)
from app.modules.benchmarks.schemas import (
    EmployeeBenchmarksOut,
    EmployeeOverviewOut,
    EmployeesPerformancePageOut,
    MyAlertsOut,
    TeamAlertsOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])

AuthUser = Depends(get_current_user)
PMUser = Depends(require_role("project_manager"))


@router.get("/my-alerts", response_model=MyAlertsOut)
def my_alerts(user: User = AuthUser, db: Session = Depends(get_db)) -> MyAlertsOut:
    return MyAlertsOut.model_validate(service.get_my_alerts(db, user))


@router.get("/team-alerts", response_model=TeamAlertsOut)
def team_alerts(_user: User = PMUser, db: Session = Depends(get_db)) -> TeamAlertsOut:
    return TeamAlertsOut.model_validate(service.get_team_alerts(db, _user))


@router.get("/employees-performance", response_model=EmployeesPerformancePageOut)
def employees_performance(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = "",
    status: str = Query("all", pattern="^(all|needs_review|on_track)$"),
    sort: str = "productivity",
    order: str = Query("asc", pattern="^(asc|desc)$"),
    cycle: str = Query("current", pattern="^(current|previous)$"),
    _user: User = PMUser,
    db: Session = Depends(get_db),
) -> EmployeesPerformancePageOut:
    """Layer 1 — comparison table. Comparison columns only (reuses the frozen
    _employee_comparison rollup); no overview/analytics fields here. `cycle`
    switches the Fri..Thu window (current for live view, previous to review
    the finished cycle — matches the pending export's options)."""
    return EmployeesPerformancePageOut.model_validate(
        service.get_employees_performance(
            db, page=page, page_size=page_size, search=search, status=status,
            sort=sort, order=order, cycle=cycle,
        )
    )


@router.get("/pending-export.xlsx")
def pending_export_xlsx(
    cycle: str = Query("previous", pattern="^(previous|current)$"),
    _user: User = PMUser,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """PM-only full-cycle Benchmark export — every benchmark activity row in
    the cycle for every employee with activity (achievers included, no
    pending > 0 filter), grouped employee -> sub-activity. Each numeric
    sub-activity gets one TOTAL row with its own achievement %; textual task
    sub-activities show detail rows only. Defaults to the previous completed
    Fri..Thu cycle (PMs export Friday morning); ?cycle=current exports the
    active one."""
    data = service.get_pending_benchmark_export(db, cycle=cycle)
    buf = build_pending_benchmark_workbook(
        data["rows"], data["cycle_start"], data["cycle_end"]
    )
    filename = (
        f"BENCHMARK REPORT {date_range_label(data['cycle_start'], data['cycle_end'])}.xlsx"
    )
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/employees/{employee_id}/overview", response_model=EmployeeOverviewOut)
def employee_overview(
    employee_id: uuid.UUID, _user: User = PMUser, db: Session = Depends(get_db)
) -> EmployeeOverviewOut:
    """Layer 2/3 — shared overview aggregation for the drawer and the route's
    Overview tab."""
    return EmployeeOverviewOut.model_validate(
        service.get_employee_overview(db, employee_id)
    )


@router.get("/employees/{employee_id}/benchmarks", response_model=EmployeeBenchmarksOut)
def employee_benchmarks(
    employee_id: uuid.UUID, _user: User = PMUser, db: Session = Depends(get_db)
) -> EmployeeBenchmarksOut:
    """Layer 3 Benchmarks tab — full weekly ledger + overdue for one employee,
    so the client reconciles backlog (same logic as the employee's own widget)."""
    return EmployeeBenchmarksOut.model_validate(
        service.get_employee_benchmarks(db, employee_id)
    )
