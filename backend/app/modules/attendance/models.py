"""Attendance record ORM model (mirrors employees/projects conventions).

One row per (employee, attendance_date). Attendance is an operational log:
DELETE hard-removes a record (no soft-delete), so uniqueness is a plain
UNIQUE(employee_id, attendance_date). total/overtime minutes are derived.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
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
    # Why a human set this day the way they did (migration 0067). Nullable: most
    # days need no explanation, and a day nobody explained must read as "no
    # reason given" rather than as an empty string somebody typed.
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # How much of this day was funded from the LEAVE POOL (migration 0083):
    # 1 a whole leave day, 0.5 a half-day leave, 0 none of it.
    #
    # `status` cannot answer this on its own, which is the whole reason the
    # column exists: a `half_day` row is "worked half a day" and says nothing
    # about what the other half was. An employee taking half a day off and an
    # office that closed at noon are the same status and different leave.
    #
    # NULL means NOT STATED, and is read as the pre-0083 rule (`leave` -> 1,
    # everything else -> 0) by `leave_balances.ledger.leave_days_for` - the one
    # function allowed to turn a row into a leave-day number. That is what makes
    # every row written before this column existed keep its current value, and
    # it is why a company-wide half day is not retroactively charged to anybody.
    leave_day_fraction: Mapped[Decimal | None] = mapped_column(
        Numeric(3, 2), nullable=True
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
        # Leave is transacted in halves and nothing else. The floor under the
        # API validation, so a direct SQL write cannot introduce 0.4 of a day.
        CheckConstraint(
            "leave_day_fraction IS NULL OR ("
            " leave_day_fraction >= 0"
            " AND leave_day_fraction <= 1"
            " AND leave_day_fraction * 2 = trunc(leave_day_fraction * 2)"
            ")",
            name="attendance_leave_fraction_half_steps",
        ),
        Index("attendance_employee_idx", "employee_id", "attendance_date"),
        Index("attendance_date_idx", "attendance_date"),
    )
