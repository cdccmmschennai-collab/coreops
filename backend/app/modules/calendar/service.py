"""Company Calendar service.

RBAC:
  all roles  read (list / get)
  manager    create / update / delete
  admin      create / update / delete
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.schemas import CalendarEventCreate, CalendarEventUpdate
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError


def _notify_all_users(db: Session, ev: CalendarEvent) -> None:
    try:
        from app.modules.notifications.service import create_notification
        user_ids = db.execute(
            select(User.id).where(User.deleted_at.is_(None), User.is_active.is_(True))
        ).scalars().all()
        label = "Holiday" if ev.event_type.value == "holiday" else "Company event"
        for uid in user_ids:
            create_notification(
                db,
                user_id=uid,
                type_="calendar_event_created",
                title=f"{label}: {ev.title}",
                message=f"{ev.title} on {ev.event_date}.",
                entity_type="calendar_event",
                entity_id=ev.id,
            )
        db.commit()
    except Exception:
        db.rollback()

def _assert_can_write(actor: User) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError("forbidden", "Only project managers can manage calendar events.", 403)


def _fetch(db: Session, event_id: uuid.UUID) -> CalendarEvent:
    ev = db.get(CalendarEvent, event_id)
    if ev is None:
        raise AppError("not_found", "Calendar event not found.", 404)
    return ev


def list_events(
    db: Session,
    *,
    date_from: date | None,
    date_to: date | None,
    event_type: CalendarEventType | None,
    limit: int,
    offset: int,
) -> tuple[list[CalendarEvent], int]:
    stmt = select(CalendarEvent)
    if date_from is not None:
        stmt = stmt.where(CalendarEvent.event_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(CalendarEvent.event_date <= date_to)
    if event_type is not None:
        stmt = stmt.where(CalendarEvent.event_type == event_type)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(CalendarEvent.event_date.asc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total


def get_event(db: Session, event_id: uuid.UUID) -> CalendarEvent:
    return _fetch(db, event_id)


def create_event(
    db: Session, actor: User, data: CalendarEventCreate
) -> CalendarEvent:
    _assert_can_write(actor)
    ev = CalendarEvent(
        event_date=data.event_date,
        title=data.title,
        event_type=data.event_type,
        description=data.description,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    _notify_all_users(db, ev)
    return ev


def update_event(
    db: Session, actor: User, event_id: uuid.UUID, data: CalendarEventUpdate
) -> CalendarEvent:
    _assert_can_write(actor)
    ev = _fetch(db, event_id)
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(ev, key, value)
    ev.updated_by = actor.id
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def delete_event(db: Session, actor: User, event_id: uuid.UUID) -> None:
    _assert_can_write(actor)
    ev = _fetch(db, event_id)
    db.delete(ev)
    db.commit()
