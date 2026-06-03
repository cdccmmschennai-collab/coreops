"""Leave Request endpoints.

  GET    /leave-requests                     list (RBAC-scoped) + filters/pagination
  POST   /leave-requests                     create (any employee/manager/admin with profile)
  GET    /leave-requests/{id}                get (RBAC-scoped)
  PATCH  /leave-requests/{id}                edit own pending (author only)
  POST   /leave-requests/{id}/cancel         cancel own pending (author only)
  POST   /leave-requests/{id}/approve        approve (manager/admin)
  POST   /leave-requests/{id}/reject         reject + optional comment (manager/admin)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.leave import service
from app.modules.leave.models import LeaveStatus
from app.modules.leave.schemas import (
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveRequestPage,
    LeaveRequestUpdate,
    LeaveReviewBody,
)
from app.modules.users.models import User

router = APIRouter(prefix="/leave-requests", tags=["leave"])

require_reviewer = require_role("admin", "manager")


@router.get("", response_model=LeaveRequestPage)
def list_leave_requests(
    employee_id: uuid.UUID | None = Query(default=None),
    status: LeaveStatus | None = Query(default=None),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestPage:
    rows, total = service.list_leave_requests(
        db,
        current,
        employee_id=employee_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return LeaveRequestPage(
        items=[LeaveRequestOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=LeaveRequestOut, status_code=201)
def create_leave_request(
    body: LeaveRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(service.create_leave_request(db, current, body))


@router.get("/{req_id}", response_model=LeaveRequestOut)
def get_leave_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(service.get_leave_request(db, current, req_id))


@router.patch("/{req_id}", response_model=LeaveRequestOut)
def update_leave_request(
    req_id: uuid.UUID,
    body: LeaveRequestUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.update_leave_request(db, current, req_id, body)
    )


@router.post("/{req_id}/cancel", response_model=LeaveRequestOut)
def cancel_leave_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(service.cancel_leave_request(db, current, req_id))


@router.post("/{req_id}/approve", response_model=LeaveRequestOut)
def approve_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.approve_leave_request(db, current, req_id, body)
    )


@router.post("/{req_id}/reject", response_model=LeaveRequestOut)
def reject_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.reject_leave_request(db, current, req_id, body)
    )
