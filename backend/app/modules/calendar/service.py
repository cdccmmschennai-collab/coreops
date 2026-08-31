"""Company Calendar service.

RBAC:
  all roles  read (list / get)
  manager    create / update / delete
  admin      create / update / delete

AUTOMATIC-REPORT RECONCILIATION (Phase 3D)
==========================================
A calendar write can turn a date the office was closed on into a working one - a
`working_day` override added to a Saturday, a holiday deleted off a weekday, an
event's type or date edited. Automatic week-off reports (`origin = auto`) already
generated for such a date are then wrong, and the 01:00 generator can never
correct them: it only ever CREATES, and an existing report always wins.

So every write path here calls
`work_reports.auto_reports.reconcile_auto_reports_for_calendar_change` with the
dates it may have re-classified, AFTER flushing its own change and BEFORE
committing. Two consequences that are the point of doing it that way:

  * the calendar row and the reconciliation share one transaction - either both
    land or neither does;
  * the direction is not decided here. The reconciler re-reads each date through
    `is_working_day` after the flush, and does nothing for a date that is still
    non-working, so a working -> closed change (where generation, not
    reconciliation, is responsible) simply finds nothing to do.
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.schemas import CalendarEventCreate, CalendarEventUpdate
from app.modules.users.models import User, UserRole
from app.modules.work_reports.auto_reports import (
    reconcile_auto_reports_for_calendar_change,
)
from app.shared.errors import AppError

_EVENT_TYPE_LABEL = {
    "holiday": "Holiday",
    "cdc_holiday": "CDC Holiday",
    "natural_hazard": "Natural Hazard",
    "working_day": "Working Day",
    "event": "Company event",
}


def _notify_all_users(db: Session, ev: CalendarEvent) -> None:
    try:
        from app.modules.notifications.service import create_notification
        user_ids = db.execute(
            select(User.id).where(User.deleted_at.is_(None), User.is_active.is_(True))
        ).scalars().all()
        label = _EVENT_TYPE_LABEL.get(ev.event_type.value, "Company event")
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
    # Flush first so the reconciler's own calendar read sees this event: a
    # `working_day` here may have just opened the office on a date whose AUTO
    # week-off reports are now stale.
    db.flush()
    reconcile_auto_reports_for_calendar_change(db, [ev.event_date], commit=False)
    db.commit()
    db.refresh(ev)
    _notify_all_users(db, ev)
    return ev


def update_event(
    db: Session, actor: User, event_id: uuid.UUID, data: CalendarEventUpdate
) -> CalendarEvent:
    _assert_can_write(actor)
    ev = _fetch(db, event_id)
    # An edit re-classifies BOTH ends when the date moves: the date the event
    # left (which may fall back to non-working - nothing to do) and the date it
    # landed on. An event_type change re-classifies the one date it is on.
    previous_date = ev.event_date
    fields = data.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(ev, key, value)
    ev.updated_by = actor.id
    db.add(ev)
    db.flush()
    reconcile_auto_reports_for_calendar_change(
        db, {previous_date, ev.event_date}, commit=False
    )
    db.commit()
    db.refresh(ev)
    return ev


def delete_event(db: Session, actor: User, event_id: uuid.UUID) -> None:
    _assert_can_write(actor)
    ev = _fetch(db, event_id)
    # Deleting a holiday re-opens the office on that date; the AUTO week-off
    # reports the holiday produced are stale from this commit on.
    event_date = ev.event_date
    db.delete(ev)
    db.flush()
    reconcile_auto_reports_for_calendar_change(db, [event_date], commit=False)
    db.commit()
