"""ReworkApprovalRequest ORM model - Rework Activity Approval (migration 0091).

One row per APPROVAL CYCLE of one report row. A report row on a sub-activity
configured with activity_master.requires_pm_approval (migration 0090) raises a
request when its report is SUBMITTED; a draft never does.

The key that ties a request to its report row is
(report_id, day_part, sub_activity_id). Task rows themselves are not a stable
identity - every draft save deletes and re-inserts them - so the row-side link
(work_report_tasks.rework_request_id) is re-stamped at each submit, exactly like
work_report_tasks.continuation_request_id.

History is append-only: a rejected cycle stays rejected; the employee's
correction opens a NEW row (cycle_no + 1, previous_request_id -> the rejected
one). The display fields are snapshots frozen at submit, so a later Activity
Master change (including removing the sub-activity from the Approval
Activities list) never rewrites what was asked or decided.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import UUIDMixin


class ReworkRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    # The row it governed was removed from the report before a decision.
    cancelled = "cancelled"


class ReworkApprovalRequest(UUIDMixin, Base):
    __tablename__ = "rework_approval_requests"

    # SET NULL: a reopened-then-deleted draft must not take the history with it.
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("daily_work_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    activity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=True
    )
    sub_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    # Snapshots, frozen at submit.
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    day_part: Mapped[str] = mapped_column(String(20), nullable=False)
    project_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    activity_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sub_activity_name: Mapped[str] = mapped_column(Text, nullable=False)
    employee_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ReworkRequestStatus.pending.value
    )
    cycle_no: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    previous_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rework_approval_requests.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    review_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="rework_approval_requests_status_valid",
        ),
        CheckConstraint(
            "day_part IN ('full_day', 'first_half', 'second_half')",
            name="rework_approval_requests_day_part_valid",
        ),
        CheckConstraint("cycle_no >= 1", name="rework_approval_requests_cycle_positive"),
        Index("rework_requests_employee_idx", "employee_id"),
        Index("rework_requests_project_idx", "project_id"),
        Index("rework_requests_status_idx", "status"),
        Index("rework_requests_report_idx", "report_id"),
        Index("rework_requests_date_idx", "report_date"),
        Index(
            "rework_requests_one_pending_uq",
            "report_id",
            "day_part",
            "sub_activity_id",
            unique=True,
            postgresql_where=text("status = 'pending' AND report_id IS NOT NULL"),
        ),
    )
