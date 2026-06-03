"""Office ORM model — one row per physical branch.

Stores timezone and shift configuration for each office. No attendance
calculations live here; this entity provides the schema foundation for
future shift-compliance and timezone-aware features (see ADR-001).

Timestamps (shift_start, shift_end) are stored as local TIME values and
interpreted relative to the office's IANA timezone string.
"""
from datetime import time

from sqlalchemy import Boolean, Index, String, Time, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class Office(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "offices"

    name: Mapped[str] = mapped_column(String, nullable=False)
    timezone: Mapped[str] = mapped_column(String, nullable=False)
    shift_start: Mapped[time] = mapped_column(Time, nullable=False)
    shift_end: Mapped[time] = mapped_column(Time, nullable=False)
    break_minutes: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )

    __table_args__ = (
        Index("offices_name_uq", "name", unique=True),
    )
