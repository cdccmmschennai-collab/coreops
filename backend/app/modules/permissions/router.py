"""Permission Request endpoints (Phase 11).

  GET  /permission-requests                      list (RBAC-scoped) + filters/pagination
  POST /permission-requests                      submit (any employee-linked user)
  GET  /permission-requests/history              one month of history + its balance
  GET  /permission-requests/balance/me           own current-month balance
  GET  /permission-requests/balance/{emp_id}     any employee's balance (PM only)
  GET  /permission-requests/{id}                 detail: names + balance context
  POST /permission-requests/{id}/cancel          cancel (author, or a PM)
  POST /permission-requests/{id}/approve         approve (PM, never own)
  POST /permission-requests/{id}/reject          reject  (PM, never own)

`/history` and the two `/balance/...` routes are declared BEFORE `/{req_id}`, or
FastAPI would match `history` as a request id and fail UUID parsing - the same
ordering `leave/router.py` relies on for its bulk POST routes.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.permissions import service
from app.modules.permissions.models import PermissionStatus
from app.modules.permissions.schemas import (
    PermissionBalanceOut,
    PermissionHistoryOut,
    PermissionRequestCreate,
    PermissionRequestDetailOut,
    PermissionRequestOut,
    PermissionRequestPage,
    PermissionReviewBody,
)
from app.modules.users.models import User

router = APIRouter(prefix="/permission-requests", tags=["permissions"])

require_reviewer = require_role("project_manager")


def _balance_out(balance) -> PermissionBalanceOut:
    return PermissionBalanceOut(
        employee_id=balance.employee_id,
        month=balance.month,
        allowance_hours=balance.allowance_hours,
        approved_hours=balance.approved_hours,
        remaining_hours=balance.remaining_hours,
    )


@router.get("", response_model=PermissionRequestPage)
def list_permission_requests(
    employee_id: uuid.UUID | None = Query(default=None),
    status: PermissionStatus | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionRequestPage:
    rows, total = service.list_permission_requests(
        db,
        current,
        employee_id=employee_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return PermissionRequestPage(
        items=[PermissionRequestOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=PermissionRequestOut, status_code=201)
def create_permission_request(
    body: PermissionRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionRequestOut:
    return PermissionRequestOut.model_validate(
        service.create_permission_request(db, current, body)
    )


@router.get("/history", response_model=PermissionHistoryOut)
def get_permission_history(
    month: date | None = Query(
        default=None,
        description="Any date in the month to report. Defaults to the current "
        "Chennai business month.",
    ),
    employee_id: uuid.UUID | None = Query(
        default=None,
        description="Whose history. Defaults to the caller; naming somebody else "
        "requires the project_manager role.",
    ),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionHistoryOut:
    """One calendar month of permission history WITH that month's balance.

    Both halves come from the same month bounds computed once server-side, and the
    rows are filtered on `permission_date` - never `created_at` - so the table and
    the figure above it can never describe different months.
    """
    return service.permission_history(
        db, current, employee_id=employee_id, month_of=month, limit=limit, offset=offset
    )


@router.get("/balance/me", response_model=PermissionBalanceOut)
def get_my_permission_balance(
    month: date | None = Query(
        default=None,
        description="Any date in the month to report. Defaults to the current "
        "Chennai business month.",
    ),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionBalanceOut:
    return _balance_out(service.my_balance(db, current, month))


@router.get("/balance/{employee_id}", response_model=PermissionBalanceOut)
def get_employee_permission_balance(
    employee_id: uuid.UUID,
    month: date | None = Query(default=None),
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> PermissionBalanceOut:
    """The balance a project manager needs to judge a pending request against.
    Read-only; the approval re-derives it under a lock regardless."""
    return _balance_out(service.employee_balance(db, current, employee_id, month))


@router.get("/{req_id}", response_model=PermissionRequestDetailOut)
def get_permission_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionRequestDetailOut:
    """The detail page's single call: the request, the employee and reviewer names,
    and the request's place in its month's balance.

    Same authorisation as the list - own requests for an employee, any for a
    project manager - so this is not a way around the list's scoping.
    """
    return service.get_permission_detail(db, current, req_id)


@router.post("/{req_id}/cancel", response_model=PermissionRequestOut)
def cancel_permission_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PermissionRequestOut:
    return PermissionRequestOut.model_validate(
        service.cancel_permission_request(db, current, req_id)
    )


@router.post("/{req_id}/approve", response_model=PermissionRequestOut)
def approve_permission_request(
    req_id: uuid.UUID,
    body: PermissionReviewBody = PermissionReviewBody(),
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> PermissionRequestOut:
    return PermissionRequestOut.model_validate(
        service.approve_permission_request(db, current, req_id, body)
    )


@router.post("/{req_id}/reject", response_model=PermissionRequestOut)
def reject_permission_request(
    req_id: uuid.UUID,
    body: PermissionReviewBody = PermissionReviewBody(),
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> PermissionRequestOut:
    return PermissionRequestOut.model_validate(
        service.reject_permission_request(db, current, req_id, body)
    )
