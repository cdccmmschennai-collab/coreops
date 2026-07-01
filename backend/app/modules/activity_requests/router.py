"""Activity request endpoints.

  POST /activity-requests                 employee — create a request
  GET  /activity-requests                 PM — list (default: pending)
  GET  /activity-requests/pending-count   PM — badge count
  POST /activity-requests/{id}/approve    PM
  POST /activity-requests/{id}/reject     PM
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.activity_requests import service
from app.modules.activity_requests.models import ActivityRequestStatus
from app.modules.activity_requests.schemas import (
    ActivityRequestCreate,
    ActivityRequestOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/activity-requests", tags=["activity-requests"])


@router.post("", response_model=ActivityRequestOut, status_code=201)
def create_activity_request(
    body: ActivityRequestCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityRequestOut:
    return ActivityRequestOut.model_validate(
        service.create_request(db, current, body)
    )


@router.get("", response_model=list[ActivityRequestOut])
def list_activity_requests(
    status: ActivityRequestStatus = ActivityRequestStatus.pending,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ActivityRequestOut]:
    return [
        ActivityRequestOut.model_validate(r)
        for r in service.list_requests(db, current, status)
    ]


@router.get("/pending-count")
def pending_count(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    return {"count": service.pending_count(db, current)}


@router.post("/{request_id}/approve", response_model=ActivityRequestOut)
def approve_activity_request(
    request_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityRequestOut:
    return ActivityRequestOut.model_validate(
        service.approve_request(db, current, request_id)
    )


@router.post("/{request_id}/reject", response_model=ActivityRequestOut)
def reject_activity_request(
    request_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ActivityRequestOut:
    return ActivityRequestOut.model_validate(
        service.reject_request(db, current, request_id)
    )
