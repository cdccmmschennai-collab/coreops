"""Leave balance endpoints (Phase 1 — manual maintenance).

  GET    /leave-balances                       manager list (search + pagination)
  GET    /leave-balances/me                     signed-in employee's own balance
  POST   /leave-balances/{employee_id}          manager set balance (+ history)
  GET    /leave-balances/{employee_id}/history   manager view change history

Editing and history are gated to project_manager; employees may only read
their own balance via /me.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.leave_balances import service
from app.modules.leave_balances.schemas import (
    LeaveBalanceHistoryPage,
    LeaveBalanceOut,
    LeaveBalancePage,
    LeaveBalanceUpdate,
    MyLeaveBalanceOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/leave-balances", tags=["leave-balances"])

require_manager = require_role("project_manager")


@router.get("", response_model=LeaveBalancePage)
def list_leave_balances(
    q: str | None = Query(default=None),
    sort_dir: str = Query(default="asc", pattern="^(asc|desc)$"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalancePage:
    items, total = service.list_balances(
        db, q=q, sort_dir=sort_dir, limit=limit, offset=offset
    )
    return LeaveBalancePage(items=items, total=total, limit=limit, offset=offset)


@router.get("/me", response_model=MyLeaveBalanceOut)
def get_my_leave_balance(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MyLeaveBalanceOut:
    return service.get_my_balance(db, current)


@router.post("/{employee_id}", response_model=LeaveBalanceOut)
def set_leave_balance(
    employee_id: uuid.UUID,
    body: LeaveBalanceUpdate,
    current: User = Depends(require_manager),
    db: Session = Depends(get_db),
) -> LeaveBalanceOut:
    return service.set_balance(db, current, employee_id, body)


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
