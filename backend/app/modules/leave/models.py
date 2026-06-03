"""Leave Request ORM model.

Status lifecycle: pending → approved | rejected | cancelled
manager_id is captured at decision time (denormalised audit column — the
requesting employee's manager may change after approval).
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
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class LeaveType(str, enum.Enum):
    casual = "casual"
    sick = "sick"
    annual = "annual"
    comp_off = "comp_off"
    unpaid = "unpaid"
    other = "other"


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class LeaveRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    leave_type: Mapped[LeaveType] = mapped_column(
        SAEnum(LeaveType, name="leave_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeaveStatus] = mapped_column(
        SAEnum(LeaveStatus, name="leave_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_order"),
        Index("leave_employee_idx", "employee_id", "start_date"),
        Index("leave_manager_idx", "manager_id", "status"),
        Index("leave_status_idx", "status"),
    )
