"""Leave Request ORM model.

Status lifecycle:
  pending  → approved | rejected | cancelled
  approved → cancellation_requested → cancelled | approved

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
    """RETIRED. The leave categories CoreOps used before Normal/Special.

    Nobody chooses one of these any more: a request's classification is derived
    from its authoritative working-day count by `leave/classification.py`, and
    that is the only classification the API accepts or exposes.

    The enum and its column survive - unchanged, and with no migration - for one
    reason: `unpaid` still means "the pool does not pay for this absence" to
    `effects.BALANCE_DEDUCTING_TYPES` and `leave_balances/ledger.py`. Rewriting
    the historical rows would silently restate past leave balances, so the
    stored values are left exactly as they were filed and simply stopped being
    read as a classification.
    """

    casual = "casual"
    sick = "sick"
    annual = "annual"
    comp_off = "comp_off"
    unpaid = "unpaid"
    other = "other"


# What a NEW request stores in the retired column, which is NOT NULL. `other`
# is the neutral member: it deducts from the pool exactly as `casual`, `annual`
# and `comp_off` did, so every request filed from here on behaves precisely as
# a request filed yesterday. The value is never read back as a classification.
RETIRED_LEAVE_TYPE = LeaveType.other


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    # Approved leave the employee has asked to withdraw. The absence still
    # stands until a project manager decides, so this counts as active leave.
    cancellation_requested = "cancellation_requested"


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
    # The project the employee's PREVIOUS WORKING DAY's Daily Work Report shows
    # them on, resolved once at creation by leave/routing.py. This is the
    # historical PROJECT only — never a frozen head id. Who may review/is
    # notified is always the project's CURRENT head_employee_id, looked up
    # fresh via app.core.authz at read/notify/approve time, so a Head
    # reassignment after this request was filed is honoured (Phase 1 spec §15).
    # NULL means no single project could be determined - the request falls
    # back to the existing PM approval flow.
    routed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_order"),
        Index("leave_employee_idx", "employee_id", "start_date"),
        Index("leave_manager_idx", "manager_id", "status"),
        Index("leave_status_idx", "status"),
        Index("leave_routed_project_idx", "routed_project_id"),
    )
