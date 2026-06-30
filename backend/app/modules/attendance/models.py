"""Attendance record ORM model (mirrors employees/projects conventions).

One row per (employee, attendance_date). Attendance is an operational log:
DELETE hard-removes a record (no soft-delete), so uniqueness is a plain
UNIQUE(employee_id, attendance_date). total/overtime minutes are derived.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent = "absent"
    half_day = "half_day"
    leave = "leave"
    holiday = "holiday"
    weekend = "weekend"
    # Comp-off: a day off granted by the manager in lieu of worked overtime.
    # Not a "worked" day (does not require a work report, doesn't block leave).
    comp_off = "comp_off"


class AttendanceRecord(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "attendance_records"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    attendance_date: Mapped[date] = mapped_column(Date, nullable=False)
    check_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    overtime_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(
            AttendanceStatus,
            name="attendance_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "attendance_date", name="attendance_emp_date_uq"),
        CheckConstraint(
            "total_minutes >= 0 AND overtime_minutes >= 0", name="attendance_minutes_nonneg"
        ),
        CheckConstraint(
            "check_out_at IS NULL OR check_in_at IS NULL OR check_out_at >= check_in_at",
            name="attendance_out_after_in",
        ),
        Index("attendance_employee_idx", "employee_id", "attendance_date"),
        Index("attendance_date_idx", "attendance_date"),
    )
