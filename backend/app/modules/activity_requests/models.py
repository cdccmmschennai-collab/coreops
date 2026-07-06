"""ActivityRequest ORM model.

A lightweight request an employee sends to a project's PM asking to be given
another activity. No approval workflow inside the work report, no activity
restrictions elsewhere — this table only records the selected activity details
and a pending/approved/rejected status. See migration 0050.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import UUIDMixin


class ActivityRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ActivityRequest(UUIDMixin, Base):
    __tablename__ = "activity_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # The work report this request belongs to. An approved request becomes a
    # normal activity row in this report. Nullable only for legacy rows.
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_work_reports.id", ondelete="CASCADE"),
        nullable=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=True
    )
    sub_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    # Legacy Task-link column — Task module removed (Phase 1); FK dropped from the
    # model so the mapper does not require the gone tasks table. Column dropped in
    # migration 0053 (Task 7).
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    tags_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    docs_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    bom_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spares_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ActivityRequestStatus.pending.value
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="activity_requests_status_valid",
        ),
        Index("activity_requests_employee_idx", "employee_id"),
        Index("activity_requests_status_idx", "status"),
        Index("activity_requests_report_idx", "report_id"),
    )
