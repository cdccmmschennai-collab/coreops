"""Notifications service.

All roles can read/manage their own notifications only.
Notifications are created internally by other services; there is no public
create endpoint.
"""
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.modules.notifications.models import Notification
from app.modules.users.models import User


def create_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    message: str,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
) -> Notification:
    notif = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        is_read=False,
    )
    db.add(notif)
    db.flush()
    return notif


def list_notifications(
    db: Session,
    actor: User,
    *,
    unread_only: bool,
    limit: int,
    offset: int,
) -> tuple[list[Notification], int]:
    stmt = select(Notification).where(Notification.user_id == actor.id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(Notification.created_at.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_unread_count(db: Session, actor: User) -> int:
    return db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == actor.id,
            Notification.is_read.is_(False),
        )
    ).scalar_one()


def mark_as_read(db: Session, actor: User, notification_id: uuid.UUID) -> Notification | None:
    notif = db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == actor.id,
        )
    ).scalar_one_or_none()
    if notif is None:
        return None
    notif.is_read = True
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


def mark_all_as_read(db: Session, actor: User) -> int:
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == actor.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.commit()
    return result.rowcount
