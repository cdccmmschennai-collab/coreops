"""Project submission ORM models."""
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class SubmissionStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


_ALLOWED_STATUS_TRANSITIONS: dict[SubmissionStatus, set[SubmissionStatus]] = {
    SubmissionStatus.draft: {SubmissionStatus.submitted},
    SubmissionStatus.submitted: {SubmissionStatus.approved, SubmissionStatus.rejected},
    SubmissionStatus.approved: set(),
    SubmissionStatus.rejected: {SubmissionStatus.draft},
}


class ProjectSubmission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_submissions"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    submission_date: Mapped[date] = mapped_column(Date, nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=SubmissionStatus.draft.value
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list["ProjectSubmissionItem"]] = relationship(
        "ProjectSubmissionItem", cascade="all, delete-orphan", lazy="select"
    )

    __table_args__ = (
        CheckConstraint("period_end >= period_start", name="project_submissions_period_order"),
        Index("project_submissions_project_idx", "project_id"),
        Index("project_submissions_status_idx", "status"),
    )


class ProjectSubmissionItem(Base):
    __tablename__ = "project_submission_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    activity_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    activity_label: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="project_submission_items_qty_pos"),
        Index("project_submission_items_submission_idx", "submission_id"),
    )
