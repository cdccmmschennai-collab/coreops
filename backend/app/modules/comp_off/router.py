"""Comp Off Request endpoints (Phase 3).

  GET  /comp-off-requests               list (PM: all; others: own) + filters
  POST /comp-off-requests               submit (any employee-linked user)
  GET  /comp-off-requests/{id}          detail (PM, or the author)
  POST /comp-off-requests/{id}/approve  approve (project manager, never own)
  POST /comp-off-requests/{id}/reject   reject with a reason (project manager, never own)
  POST /comp-off-requests/{id}/cancel   withdraw a pending request (author)

Authority is enforced in the service on every path, not by the dependency, so
every refusal carries the same message whichever route was called.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.comp_off import service
from app.modules.comp_off.models import CompOffStatus
from app.modules.comp_off.schemas import (
    CompOffApproveBody,
    CompOffRejectBody,
    CompOffRequestCreate,
    CompOffRequestOut,
    CompOffRequestPage,
)
from app.modules.users.models import User

router = APIRouter(prefix="/comp-off-requests", tags=["comp-off"])


@router.get("", response_model=CompOffRequestPage)
def list_comp_off_requests(
    employee_id: uuid.UUID | None = Query(default=None),
    status: CompOffStatus | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    exclude_self: bool = Query(
        default=False,
        description="Drop the caller's own requests - what a review queue passes.",
    ),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestPage:
    rows, total = service.list_comp_off_requests(
        db, current, employee_id=employee_id, status=status,
        limit=limit, offset=offset, exclude_self=exclude_self,
    )
    return CompOffRequestPage(
        items=[CompOffRequestOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.post("", response_model=CompOffRequestOut, status_code=201)
def create_comp_off_request(
    body: CompOffRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestOut:
    return CompOffRequestOut.model_validate(service.create_comp_off_request(db, current, body))


@router.get("/{req_id}", response_model=CompOffRequestOut)
def get_comp_off_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestOut:
    return CompOffRequestOut.model_validate(service.get_comp_off_request(db, current, req_id))


@router.post("/{req_id}/approve", response_model=CompOffRequestOut)
def approve_comp_off_request(
    req_id: uuid.UUID,
    body: CompOffApproveBody = CompOffApproveBody(),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestOut:
    return CompOffRequestOut.model_validate(
        service.approve_comp_off_request(db, current, req_id, body)
    )


@router.post("/{req_id}/reject", response_model=CompOffRequestOut)
def reject_comp_off_request(
    req_id: uuid.UUID,
    body: CompOffRejectBody,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestOut:
    return CompOffRequestOut.model_validate(
        service.reject_comp_off_request(db, current, req_id, body)
    )


@router.post("/{req_id}/cancel", response_model=CompOffRequestOut)
def cancel_comp_off_request(
    req_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CompOffRequestOut:
    return CompOffRequestOut.model_validate(service.cancel_comp_off_request(db, current, req_id))
