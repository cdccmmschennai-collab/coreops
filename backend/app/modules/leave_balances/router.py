"""Leave balance endpoints - month-aware reads plus the two PM decisions.

  GET  /leave-balances                        manager list for a month
  GET  /leave-balances/me                      own balance for a month
  GET  /leave-balances/{employee_id}           one employee's balance (PM)
  POST /leave-balances/{employee_id}           PM correction (+ history)
  GET  /leave-balances/{employee_id}/allocations  every rate they have been on (PM)
  PUT  /leave-balances/{employee_id}/allocation   set `Leave/month` (PM)
  GET  /leave-balances/{employee_id}/history      PM correction trail

`/me` is declared BEFORE `/{employee_id}` or FastAPI would try to parse "me" as a
UUID - the same ordering `permissions/router.py` relies on.

Editing, allocation and history stay gated to project_manager exactly as before;
employees may only read their own balance via `/me`. Phase 3 broadened nothing.

THE `month` PARAMETER
=====================
Any date inside the month, matching the convention `permission-requests` already
uses (`?month=2026-08-01`), so the attendance page can send one value to both
APIs. Omitted means the current Chennai business month, resolved server-side -
never the browser's month.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.leave_balances import service
from app.modules.leave_balances.schemas import (
    LeaveAllocationOut,
    LeaveAllocationPage,
    LeaveAllocationUpdate,
    LeaveBalanceHistoryPage,
    LeaveBalanceOut,
    LeaveBalancePage,
    LeaveBalanceUpdate,
    MyLeaveBalanceOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/leave-balances", tags=["leave-balances"])

require_manager = require_role("project_manager")

_MONTH_HELP = (
    "Any date in the calendar month to report. Defaults to the current Chennai "
    "business month."
)


@router.get("", response_model=LeaveBalancePage)
def list_leave_balances(
    month: date | None = Query(default=None, description=_MONTH_HELP),
    q: str | None = Query(default=None),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalancePage:
    items, total, resolved = service.list_balances(
        db, month=month, q=q, sort_dir=sort_dir, limit=limit, offset=offset
    )
    return LeaveBalancePage(
        items=items, total=total, limit=limit, offset=offset, month=resolved
    )


@router.get("/me", response_model=MyLeaveBalanceOut)
def get_my_leave_balance(
    month: date | None = Query(default=None, description=_MONTH_HELP),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyLeaveBalanceOut:
    """The signed-in employee's own balance for one month.

    A pure read. It derives the figure and writes nothing - asking for a month
    can never accrue that month's allocation.
    """
    return service.get_my_balance(db, current, month)


@router.get("/{employee_id}", response_model=LeaveBalanceOut)
def get_leave_balance(
    employee_id: uuid.UUID,
    month: date | None = Query(default=None, description=_MONTH_HELP),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalanceOut:
    return service.get_employee_balance(db, employee_id, month)


@router.post("/{employee_id}", response_model=LeaveBalanceOut)
def set_leave_balance(
    employee_id: uuid.UUID,
    body: LeaveBalanceUpdate,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalanceOut:
    """PM correction. The body still carries the TARGET balance the manager
    wants; the service stores the difference as an adjustment so the monthly
    allocation underneath it survives."""
    return service.set_balance(db, current, employee_id, body)


@router.get("/{employee_id}/allocations", response_model=LeaveAllocationPage)
def list_leave_allocations(
    employee_id: uuid.UUID,
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveAllocationPage:
    return service.list_allocations(db, employee_id)


@router.put("/{employee_id}/allocation", response_model=LeaveAllocationOut)
def set_leave_allocation(
    employee_id: uuid.UUID,
    body: LeaveAllocationUpdate,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveAllocationOut:
    """Set `Leave/month` from `effective_from` (a first-of-month) onwards.

    PUT rather than POST because it is idempotent per effective month: sending
    the same month twice settles on one row rather than stacking two rates for
    one month. Earlier months keep the rate they were on.
    """
    return service.set_allocation(db, current, employee_id, body)


@router.get("/{employee_id}/history", response_model=LeaveBalanceHistoryPage)
def list_leave_balance_history(
    employee_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalanceHistoryPage:
    items, total = service.list_history(db, employee_id, limit=limit, offset=offset)
    return LeaveBalanceHistoryPage(
        items=items, total=total, limit=limit, offset=offset
    )
