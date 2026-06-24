"""Leave balance ORM models (Phase 1 — manually maintained, no accrual).

`EmployeeLeaveBalance` holds one active row per employee: `available_leave` is
the source of truth for the figure shown to the employee. Every change is
recorded in `EmployeeLeaveBalanceHistory`, an append-only trail (immutable —
only created_at is tracked).
"""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class EmployeeLeaveBalance(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "employee_leave_balances"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    # May be negative: a negative balance represents loss-of-pay (e.g. -0.5 for
    # a half-day LOP, -2 for two days of excess leave taken).
    available_leave: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )

    __table_args__ = (
        Index("leave_balance_employee_uq", "employee_id", unique=True),
    )


class EmployeeLeaveBalanceHistory(UUIDMixin, Base):
    __tablename__ = "employee_leave_balance_history"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    old_balance: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    new_balance: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("leave_balance_history_employee_idx", "employee_id", "created_at"),
    )
