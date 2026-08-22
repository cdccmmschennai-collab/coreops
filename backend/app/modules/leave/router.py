"""Leave Request endpoints.

  GET    /leave-requests                     list (RBAC-scoped) + filters/pagination
  POST   /leave-requests                     create (any employee/manager/admin with profile)
  GET    /leave-requests/{id}                get (RBAC-scoped)
  PATCH  /leave-requests/{id}                edit own pending (author only)
  POST   /leave-requests/{id}/cancel         cancel own pending (author only)
  POST   /leave-requests/{id}/approve        approve (manager/admin)
  POST   /leave-requests/{id}/reject         reject + optional comment (manager/admin)

  Approved-leave withdrawal:
  POST   /leave-requests/{id}/request-cancellation  ask to withdraw (author only)
  POST   /leave-requests/{id}/approve-cancellation  cancel the leave (manager)
  POST   /leave-requests/{id}/reject-cancellation   keep the leave (manager)
  POST   /leave-requests/attendance-summary         read-only queue info (manager)
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
    AttendanceSummaryRequest,
    AttendanceSummaryResponse,
    DeliverableImpactRequest,
    DeliverableImpactResponse,
    LeaveRequestCreate,
    LeaveRequestOut,
    LeaveRequestPage,
    LeaveRequestUpdate,
    LeaveReviewBody,
)
from app.modules.users.models import User

router = APIRouter(prefix="/leave-requests", tags=["leave"])

require_reviewer = require_role("project_manager")


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


@router.post("/deliverable-impact", response_model=DeliverableImpactResponse)
def deliverable_impact(
    body: DeliverableImpactRequest,
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> DeliverableImpactResponse:
    """Decision-support: which of the given (displayed) leave requests overlap
    a Planned project deliverable. Project-manager only; informational."""
    items = service.deliverable_impacts(db, current, body.leave_request_ids)
    return DeliverableImpactResponse(items=items)


@router.post("/attendance-summary", response_model=AttendanceSummaryResponse)
def attendance_summary(
    body: AttendanceSummaryRequest,
    current: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> AttendanceSummaryResponse:
    """Read-only: attendance already recorded across each displayed leave
    request's dates, one word per row. Never modifies attendance."""
    return AttendanceSummaryResponse(
        items=service.attendance_summaries(db, current, body)
    )


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


@router.post("/{req_id}/request-cancellation", response_model=LeaveRequestOut)
def request_leave_cancellation(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.request_leave_cancellation(db, current, req_id)
    )


@router.post("/{req_id}/approve-cancellation", response_model=LeaveRequestOut)
def approve_leave_cancellation(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.approve_leave_cancellation(db, current, req_id)
    )


@router.post("/{req_id}/reject-cancellation", response_model=LeaveRequestOut)
def reject_leave_cancellation(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.reject_leave_cancellation(db, current, req_id)
    )


@router.post("/{req_id}/approve", response_model=LeaveRequestOut)
def approve_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.approve_leave_request(db, current, req_id, body)
    )


@router.post("/{req_id}/reject", response_model=LeaveRequestOut)
def reject_leave_request(
    req_id: uuid.UUID,
    body: LeaveReviewBody = LeaveReviewBody(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LeaveRequestOut:
    return LeaveRequestOut.model_validate(
        service.reject_leave_request(db, current, req_id, body)
    )
