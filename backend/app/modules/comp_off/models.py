"""Comp Off Request ORM model (Comp Off Phase 2 - data foundation only).

An employee who worked an eligible day asks for one day off in return, naming
BOTH dates in one request: the day they worked (`worked_date`) and the day they
want off (`off_date`). A PM approves or rejects the request as a whole.

Status lifecycle:
  pending  -> approved | rejected | cancelled
  approved -> cancelled

THE ROW IS THE CREDIT - NO LEDGER, NO BALANCE COLUMN
====================================================
Only an `approved` row is a credit, and it is already spent on its own
`off_date`. Pending, rejected and cancelled rows grant nothing, by status alone.
Whether the day off has been taken is read off `off_date` (and, from the
attendance phase on, the attendance row it marks) - never stored as a second
fact that could drift from the first. Same reasoning as `permission_requests`
(migration 0068): a derived figure cannot disagree with the rows it sums.

The original work report stays on `worked_date`. Nothing here copies, moves or
references a report; proving the day was worked is a service-phase rule.

`manager_id` is the reviewer, captured at decision time, exactly as on
`leave_requests` / `permission_requests`; `manager_comment` carries the decision
note, including a rejection reason. `created_at` is the requested-at timestamp.

Legacy PM-entered `comp_off` attendance rows are NOT represented here: they name
no worked date, so no credit can be reconstructed from them.
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


class CompOffStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


# The statuses that hold a date. A worked day can back at most one of these and
# an off day can be claimed by at most one - see the partial unique indexes.
# Rejected and cancelled rows are history and may repeat freely.
LIVE_COMP_OFF_STATUSES = (CompOffStatus.pending, CompOffStatus.approved)

# The same set as SQL, shared by the model and the migration's index predicate.
LIVE_COMP_OFF_PREDICATE = "status IN ('pending', 'approved')"


class CompOffRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "comp_off_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # The day the employee worked to earn the comp off.
    worked_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The day the employee wants off in return.
    off_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CompOffStatus] = mapped_column(
        SAEnum(
            CompOffStatus,
            name="comp_off_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("worked_date <> off_date", name="comp_off_dates_differ"),
        # A pending request carries no decision; an approved or rejected one
        # always says when it was decided. `manager_id` is not required on a
        # decided row because the reviewer's employee record may later be
        # removed (ON DELETE SET NULL). A cancelled row may or may not have been
        # reviewed first, so it is left unconstrained.
        CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL AND manager_id IS NULL)"
            " OR (status IN ('approved', 'rejected') AND reviewed_at IS NOT NULL)"
            " OR status = 'cancelled'",
            name="comp_off_decision_consistent",
        ),
        Index(
            "comp_off_live_worked_date_uq",
            "employee_id",
            "worked_date",
            unique=True,
            postgresql_where=text(LIVE_COMP_OFF_PREDICATE),
        ),
        Index(
            "comp_off_live_off_date_uq",
            "employee_id",
            "off_date",
            unique=True,
            postgresql_where=text(LIVE_COMP_OFF_PREDICATE),
        ),
        Index("comp_off_status_idx", "status"),
        Index("comp_off_manager_idx", "manager_id", "status"),
    )
