"""Permission Request ORM model (Phase 11).

"Permission" is the attendance sense, NOT an RBAC capability: an hour or two of
sanctioned absence inside an otherwise normal working day. A permission day stays
`present` in `attendance_records` - the hours are a separate attribute, held here.

Status lifecycle (four states, no fifth):
  pending  -> approved | rejected | cancelled
  approved -> cancelled            (restores the hours)

Leave has a `cancellation_requested` state because an approved multi-day absence
stands until a manager rules on its withdrawal. One or two hours has nothing to
hold open, so cancellation here is a single step.

`manager_id` is the reviewer, captured at decision time (denormalised audit
column, exactly as `leave_requests.manager_id` is - the employee's manager may
change after the decision). `created_at` is the requested-at timestamp; there is
no second column for it.
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
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class PermissionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class PermissionRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permission_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # A permission is always a single day. There is no range: two hours off on
    # Monday and one on Tuesday are two separate decisions with two separate
    # balances to check.
    permission_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Whole hours, 1 or 2 - enforced by the check constraint below as well as by
    # the API schema, so no script or fixture can create a 30-minute permission.
    duration_hours: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PermissionStatus] = mapped_column(
        SAEnum(
            PermissionStatus,
            name="permission_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The project the employee's latest valid Daily Work Report evidence shows
    # them on, resolved once at creation (Phase 4B) by the SAME resolver Leave
    # uses - leave/routing.py::resolve_routed_project. Historical only, never a
    # frozen approver: who reviews is always the project's CURRENT
    # head_employee_id, looked up fresh via app.core.authz at read/review time.
    # NULL means no single project could be determined and the request falls
    # back to the existing PM / reporting_pm_id approval flow.
    routed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("duration_hours IN (1, 2)", name="permission_duration_1h_or_2h"),
        Index("permission_employee_date_idx", "employee_id", "permission_date"),
        Index("permission_status_idx", "status"),
        Index("permission_manager_idx", "manager_id", "status"),
        Index("permission_routed_project_idx", "routed_project_id"),
    )
