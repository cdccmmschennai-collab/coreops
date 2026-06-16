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
    target_url: str | None = None,
) -> Notification:
    """One-off event notification (report submitted/rejected/etc.) — always
    inserts a new row. For an ongoing *condition* that should have at most
    one active notification (benchmark shortfall, overdue task), use
    `upsert_notification`/`resolve_notification` instead."""
    notif = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        target_url=target_url,
        is_read=False,
    )
    db.add(notif)
    db.flush()
    return notif


def _find_active(
    db: Session, *, user_id: uuid.UUID, type_: str, entity_type: str, entity_id: uuid.UUID,
) -> Notification | None:
    return db.execute(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.type == type_,
            Notification.entity_type == entity_type,
            Notification.entity_id == entity_id,
            Notification.resolved_at.is_(None),
        )
    ).scalar_one_or_none()


def upsert_notification(
    db: Session,
    *,
    user_id: uuid.UUID,
    type_: str,
    title: str,
    message: str,
    severity: str = "INFO",
    entity_type: str,
    entity_id: uuid.UUID,
    target_url: str | None = None,
) -> Notification:
    """One persistent notification per (user_id, entity_type, entity_id,
    type_) condition. If an active (unresolved) one already exists, updates
    its message/severity/title in place instead of inserting a duplicate —
    a daily re-check of an ongoing shortfall/overdue item should not spam
    the notification center with a new row every time."""
    existing = _find_active(db, user_id=user_id, type_=type_, entity_type=entity_type, entity_id=entity_id)
    if existing is not None:
        existing.title = title
        existing.message = message
        existing.severity = severity
        existing.target_url = target_url
        db.add(existing)
        db.flush()
        return existing
    notif = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        message=message,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        target_url=target_url,
        is_read=False,
    )
    db.add(notif)
    db.flush()
    return notif


def resolve_notification(
    db: Session, *, user_id: uuid.UUID, type_: str, entity_type: str, entity_id: uuid.UUID,
) -> Notification | None:
    """Stamps resolved_at on the matching active notification, if any — the
    condition (benchmark met, task completed) has cleared."""
    existing = _find_active(db, user_id=user_id, type_=type_, entity_type=entity_type, entity_id=entity_id)
    if existing is None:
        return None
    existing.resolved_at = func.now()
    db.add(existing)
    db.flush()
    return existing


def list_notifications(
    db: Session,
    actor: User,
    *,
    unread_only: bool,
    limit: int,
    offset: int,
) -> tuple[list[Notification], int]:
    # Default view excludes resolved conditions (benchmark met, task
    # completed); one-off event notifications never get resolved_at set, so
    # they're unaffected by this filter.
    stmt = select(Notification).where(
        Notification.user_id == actor.id, Notification.resolved_at.is_(None),
    )
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
            Notification.resolved_at.is_(None),
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
