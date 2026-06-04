"""Notification endpoints.

  GET   /notifications                  list own notifications (filterable unread)
  GET   /notifications/unread-count     unread badge count
  POST  /notifications/{id}/read        mark single notification read
  POST  /notifications/read-all         mark all notifications read
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.notifications import service
from app.modules.notifications.schemas import (
    NotificationOut,
    NotificationPage,
    UnreadCountOut,
)
from app.modules.users.models import User
from app.shared.errors import AppError

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
def list_notifications(
    unread_only: bool = Query(default=False),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPage:
    rows, total = service.list_notifications(
        db, current, unread_only=unread_only, limit=limit, offset=offset
    )
    return NotificationPage(
        items=[NotificationOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
def unread_count(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountOut:
    return UnreadCountOut(count=service.get_unread_count(db, current))


@router.post("/read-all", response_model=UnreadCountOut)
def mark_all_read(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UnreadCountOut:
    service.mark_all_as_read(db, current)
    return UnreadCountOut(count=0)


@router.post("/{notification_id}/read", response_model=NotificationOut)
def mark_read(
    notification_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationOut:
    notif = service.mark_as_read(db, current, notification_id)
    if notif is None:
        raise AppError("not_found", "Notification not found.", 404)
    return NotificationOut.model_validate(notif)
