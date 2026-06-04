"""Company Calendar endpoints.

  GET    /calendar-events          list events (all roles, filterable by from/to/type)
  POST   /calendar-events          create event (manager + admin)
  GET    /calendar-events/{id}     get single event (all roles)
  PATCH  /calendar-events/{id}     update event (manager + admin)
  DELETE /calendar-events/{id}     delete event (manager + admin)
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.calendar import service
from app.modules.calendar.models import CalendarEventType
from app.modules.calendar.schemas import (
    CalendarEventCreate,
    CalendarEventOut,
    CalendarEventPage,
    CalendarEventUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/calendar-events", tags=["calendar"])


@router.get("", response_model=CalendarEventPage)
def list_events(
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    event_type: CalendarEventType | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=366),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventPage:
    rows, total = service.list_events(
        db,
        date_from=date_from,
        date_to=date_to,
        event_type=event_type,
        limit=limit,
        offset=offset,
    )
    return CalendarEventPage(
        items=[CalendarEventOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CalendarEventOut, status_code=201)
def create_event(
    body: CalendarEventCreate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventOut:
    return CalendarEventOut.model_validate(service.create_event(db, current, body))


@router.get("/{event_id}", response_model=CalendarEventOut)
def get_event(
    event_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventOut:
    return CalendarEventOut.model_validate(service.get_event(db, event_id))


@router.patch("/{event_id}", response_model=CalendarEventOut)
def update_event(
    event_id: uuid.UUID,
    body: CalendarEventUpdate,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CalendarEventOut:
    return CalendarEventOut.model_validate(service.update_event(db, current, event_id, body))


@router.delete("/{event_id}", status_code=204)
def delete_event(
    event_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.delete_event(db, current, event_id)
    return Response(status_code=204)
