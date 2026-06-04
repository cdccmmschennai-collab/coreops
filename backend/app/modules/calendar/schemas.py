from datetime import date, datetime
from typing import Optional
import uuid

from pydantic import BaseModel, field_validator

from app.modules.calendar.models import CalendarEventType


class CalendarEventCreate(BaseModel):
    event_date: date
    title: str
    event_type: CalendarEventType = CalendarEventType.holiday
    description: Optional[str] = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Title cannot be blank.")
        return v.strip()


class CalendarEventUpdate(BaseModel):
    event_date: Optional[date] = None
    title: Optional[str] = None
    event_type: Optional[CalendarEventType] = None
    description: Optional[str] = None


class CalendarEventOut(BaseModel):
    id: uuid.UUID
    event_date: date
    title: str
    event_type: CalendarEventType
    description: Optional[str]
    created_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CalendarEventPage(BaseModel):
    items: list[CalendarEventOut]
    total: int
    limit: int
    offset: int
