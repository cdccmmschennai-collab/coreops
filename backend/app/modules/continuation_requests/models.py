"""ContinuationRequest ORM model - Lump-sum Activity Continuation Approval
(Phase 2).

A dedicated request/approval record. Reuses the existing WorkItem
task-continuation engine (app.modules.work_reports.work_items) as its
subject and the existing Project Head authorization (app.core.authz) +
notifications (app.modules.notifications.service) infrastructure - this
table only adds the missing approval gate + audit trail. Deliberately NOT
built on leave_requests (leave-specific: leave_type, date-range, balance
ledger) or activity_requests (a different action - requesting a NEW
activity, not continuing an existing one). See migration 0074.
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


class ContinuationRequestStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ContinuationRequest(UUIDMixin, Base):
    __tablename__ = "continuation_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # The specific activity instance this approval applies to. RESTRICT: a
    # WorkItem cannot be deleted while a continuation request still
    # references it (mirrors work_report_tasks.work_item_id's own RESTRICT).
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=False
    )
    # Denormalised from the WorkItem so routing/scoping queries never need a
    # join. The project WHO reviews is resolved against - always the
    # project's CURRENT head_employee_id via app.core.authz, never a frozen
    # head id (matches leave_requests.routed_project_id's model exactly: this
    # column is the historical PROJECT only).
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    sub_activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    # Audit snapshot of the WorkItem at request time - never re-read from the
    # WorkItem afterward (WorkItem.due_date is itself frozen at creation, so
    # this can never drift from it).
    original_report_date: Mapped[date] = mapped_column(Date, nullable=False)
    allowed_duration_days: Mapped[int] = mapped_column(Integer, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    # The report date the employee was attempting to continue on when the
    # approval gate blocked them.
    continuation_date: Mapped[date] = mapped_column(Date, nullable=False)

    # VARCHAR + CHECK (not a native Postgres enum) - follows the
    # activity_requests.status / benchmark_type / report_mode precedent.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ContinuationRequestStatus.pending.value
    )
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="continuation_requests_status_valid",
        ),
        # There is deliberately NO "continuation_date > due_date" check: the
        # allowed duration is spent in WORK DAYS (distinct dates actually
        # worked), so a request can legitimately be raised on a date at or
        # before the frozen calendar due_date - e.g. a 3-day lump-sum started on
        # a Friday and worked Fri/Sat/Sun has spent its allowance by Monday,
        # while due_date skipped the weekend to Tuesday. Migration 0075 dropped
        # that constraint; work_items.count_work_days is the real rule.
        Index("continuation_requests_employee_idx", "employee_id"),
        Index("continuation_requests_work_item_idx", "work_item_id"),
        Index("continuation_requests_project_idx", "project_id"),
        Index("continuation_requests_status_idx", "status"),
        # One PENDING request per WorkItem - the DB-level guard for "no
        # duplicate pending continuation requests" (service.py pre-checks the
        # same predicate for a clean error message; this is the authoritative
        # guard against a concurrent/duplicate insert).
        Index(
            "continuation_requests_one_pending_per_item_uq",
            "work_item_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )
