"""Leave balance ORM models.

THE LEDGER (migration 0069)
===========================
The employee's available leave is DERIVED, one month at a time, by
`leave_balances/ledger.py`:

    closing(M) = carry_in(M) + allocation(M) + adjustment(M) - consumed(M)

Two tables feed it, and neither stores a balance:

  `EmployeeLeaveAllocation`  the employee's `Leave/month`, effective-dated. One
                             row per POLICY CHANGE, never one per month, so
                             raising someone to 2 d/month in March cannot
                             rewrite what January and February accrued.
  `EmployeeLeaveAdjustment`  a signed one-off correction posted to one month -
                             the PM's manual correction, and the opening balances
                             carried over by migration 0069. Append-only.

Consumption is not stored either: it is counted from the `attendance_records`
rows an approved leave writes, so cancelling a leave restores the balance by
removing those rows and cannot drift or double-restore.

`EmployeeLeaveBalanceHistory` is unchanged and still written on every PM
correction - employee, old, new, reason, updated_by, timestamp.

`EmployeeLeaveBalance` is the PRE-LEDGER SNAPSHOT. Migration 0069 carried each
of its values into an opening adjustment and stopped reading it; it is kept,
still populated, purely as the rollback path until the derived figures have been
verified against it in production. Nothing writes it any more. Do not read it -
`ledger.closing_balance` is the only authority.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class EmployeeLeaveAllocation(UUIDMixin, TimestampMixin, Base):
    """One employee's `Leave/month`, from `effective_from` onwards.

    EFFECTIVE-DATED, NOT MONTHLY. A row is written when the POLICY changes, not
    when a month passes: an employee on 1 d/month who becomes eligible for 2 in
    March has exactly two rows, and the ledger resolves any month by taking the
    newest row whose `effective_from` is on or before that month. That is what
    keeps January and February on 1 d/month forever, however often the current
    figure is edited afterwards.

    `effective_from` is always the FIRST of a month (enforced below), because
    allocation is granted per calendar month and a mid-month effective date would
    make "what did March accrue" ambiguous.

    An employee with no row at all accrues nothing and is not broken by that -
    they simply carry their balance forward untouched, which is exactly how every
    employee behaved before this table existed.
    """

    __tablename__ = "employee_leave_allocations"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    # Fractional allocations are representable (0.5 d/month) because the rest of
    # the leave system already deals in halves. Never negative: an allocation is
    # a grant, and a deduction is an adjustment.
    monthly_days: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, server_default=text("0")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "date_part('day', effective_from) = 1",
            name="leave_allocation_effective_month_start",
        ),
        CheckConstraint("monthly_days >= 0", name="leave_allocation_nonneg"),
        Index(
            "leave_allocation_employee_month_uq",
            "employee_id",
            "effective_from",
            unique=True,
        ),
    )


class EmployeeLeaveAdjustment(UUIDMixin, Base):
    """A signed one-off correction to one employee's balance, in one month.

    Append-only and immutable, like the history table beside it: a correction is
    an event, and re-stating a month's balance is another event rather than an
    edit of the first. `days` is the DELTA, not a target - that is what lets a
    correction coexist with the automatic accrual instead of replacing it, so
    October still receives its `Leave/month` on top of a September the PM
    corrected downwards.

    SIGNED AND UNBOUNDED BELOW. The existing system allows a negative balance
    (loss-of-pay), so there is deliberately no `days >= 0` constraint here and no
    non-negative constraint on the derived total either.

    Also the home of the opening balances migration 0069 carried over from
    `employee_leave_balances`, which is why the reason is mandatory: every row in
    this table can say where it came from.
    """

    __tablename__ = "employee_leave_adjustments"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    # The month the correction belongs to, always its first day. A correction
    # made in September stays in September even if it is examined next year.
    effective_month: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "date_part('day', effective_month) = 1",
            name="leave_adjustment_month_start",
        ),
        Index(
            "leave_adjustment_employee_month_idx", "employee_id", "effective_month"
        ),
    )


class EmployeeLeaveBalance(UUIDMixin, TimestampMixin, Base):
    """PRE-LEDGER SNAPSHOT. Frozen by migration 0069 - read by nothing.

    See the module docstring. Kept only so the pre-ledger figures remain
    recoverable; `ledger.closing_balance` is the authority.
    """

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
