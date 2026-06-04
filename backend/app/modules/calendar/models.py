"""Company Calendar Event ORM model.

Managers and admins create entries; all roles can read.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum as SAEnum, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class CalendarEventType(str, enum.Enum):
    holiday = "holiday"
    event = "event"


class CalendarEvent(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "company_calendar_events"

    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[CalendarEventType] = mapped_column(
        SAEnum(CalendarEventType, name="calendar_event_type",
               values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'holiday'"),
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
