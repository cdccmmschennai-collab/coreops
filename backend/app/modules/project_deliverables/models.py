"""ProjectDeliverable ORM model."""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class DeliverableStatus(str, enum.Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class ProjectDeliverable(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_deliverables"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    target_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    owner_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[DeliverableStatus] = mapped_column(
        SAEnum(
            DeliverableStatus,
            name="deliverable_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=DeliverableStatus.pending.value,
    )
    completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("project_deliverables_project_idx", "project_id"),
        Index("project_deliverables_owner_idx", "owner_employee_id"),
        Index("project_deliverables_status_idx", "status"),
    )


# Field-name constants used as values for DeliverableChange.field
class DeliverableChangeField:
    PLANNED_START_DATE = "planned_start_date"
    DUE_DATE = "due_date"
    STATUS = "status"


class DeliverableChange(Base):
    """Append-only log of every tracked deliverable edit.

    Written whenever the planned start date, due date, or status (reversal
    from completed) changes. Never updated or deleted — the audit trail is
    immutable. Mirrors ProjectPlannedDateChange.
    """
    __tablename__ = "deliverable_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    deliverable_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("project_deliverables.id", ondelete="CASCADE"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(50), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("deliverable_changes_deliverable_idx", "deliverable_id"),
    )
