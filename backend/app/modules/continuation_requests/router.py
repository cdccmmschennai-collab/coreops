"""Continuation-request endpoints (Lump-sum Activity Continuation Approval).

  POST  /continuation-requests                employee - request approval to continue
  GET   /continuation-requests/pending        PM / Project Head - pending queue
  GET   /continuation-requests                PM / Project Head - history (All Requests)
  GET   /continuation-requests/{id}           employee (own) or PM / Project Head
  POST  /continuation-requests/{id}/approve   PM / Project Head
  POST  /continuation-requests/{id}/reject    PM / Project Head

`/pending` is registered before `/{request_id}` so it is never swallowed by
the dynamic path (same ordering convention as activity_requests' `/mine` and
`/pending-count`).
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.continuation_requests import service
from app.modules.continuation_requests.schemas import (
    ContinuationRequestCreate,
    ContinuationRequestOut,
    ContinuationRequestPage,
    ContinuationReviewBody,
)
from app.modules.users.models import User

router = APIRouter(prefix="/continuation-requests", tags=["continuation-requests"])


@router.post("", response_model=ContinuationRequestOut, status_code=201)
def create_continuation_request(
    body: ContinuationRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.create_continuation_request(db, current, body)
    )


@router.get("/pending", response_model=list[ContinuationRequestOut])
def list_pending_continuation_requests(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContinuationRequestOut]:
    return [ContinuationRequestOut.model_validate(r) for r in service.list_pending(db, current)]


@router.get("", response_model=ContinuationRequestPage)
def list_continuation_requests(
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestPage:
    rows, total = service.list_all(db, current, status=status, limit=limit, offset=offset)
    return ContinuationRequestPage(
        items=[ContinuationRequestOut.model_validate(r) for r in rows],
        total=total, limit=limit, offset=offset,
    )


@router.get("/{request_id}", response_model=ContinuationRequestOut)
def get_continuation_request(
    request_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.get_continuation_request(db, current, request_id)
    )


@router.post("/{request_id}/approve", response_model=ContinuationRequestOut)
def approve_continuation_request(
    request_id: uuid.UUID,
    body: ContinuationReviewBody,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.approve_continuation_request(db, current, request_id, body.comment)
    )


@router.post("/{request_id}/reject", response_model=ContinuationRequestOut)
def reject_continuation_request(
    request_id: uuid.UUID,
    body: ContinuationReviewBody,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContinuationRequestOut:
    return ContinuationRequestOut.model_validate(
        service.reject_continuation_request(db, current, request_id, body.comment)
    )
