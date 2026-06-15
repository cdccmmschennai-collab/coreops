"""Project Activity ORM model — Phase B Deliverable Activity Tracker."""
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


ACTIVITY_STATUS_OPEN        = "open"
ACTIVITY_STATUS_IN_PROGRESS = "in_progress"
ACTIVITY_STATUS_CLOSED      = "closed"

VALID_ACTIVITY_STATUSES = {
    ACTIVITY_STATUS_OPEN,
    ACTIVITY_STATUS_IN_PROGRESS,
    ACTIVITY_STATUS_CLOSED,
}


class ProjectActivity(Base):
    __tablename__ = "project_activities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid()
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    activity_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_types.id", ondelete="SET NULL"), nullable=True
    )
    activity_type_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot
    title: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=ACTIVITY_STATUS_OPEN
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    assigned_to_name: Mapped[str | None] = mapped_column(Text, nullable=True)  # snapshot
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('open', 'in_progress', 'closed')",
            name="project_activities_status_valid",
        ),
        Index("project_activities_project_idx", "project_id"),
        Index("project_activities_status_idx",  "status"),
        Index("project_activities_assignee_idx","assigned_to_id"),
    )
