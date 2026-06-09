"""Task ORM model — global task assignments (Phase 9A MVP).

One row per task with a single assignee. Operational log (no soft-delete).
"""
import enum
import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum as SAEnum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.modules.employees.models import Employee


class TaskStatus(str, enum.Enum):
    open = "open"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"


class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class Task(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    assigned_to_employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    assigned_by_employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(
            TaskStatus,
            name="task_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=TaskStatus.open.value,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        SAEnum(
            TaskPriority,
            name="task_priority",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=TaskPriority.medium.value,
    )
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Read-only relationships for resolving names; never written through.
    assigned_to: Mapped["Employee"] = relationship(
        "Employee", foreign_keys="Task.assigned_to_employee_id", viewonly=True
    )
    assigned_by: Mapped["Employee"] = relationship(
        "Employee", foreign_keys="Task.assigned_by_employee_id", viewonly=True
    )

    __table_args__ = (
        Index("tasks_assigned_to_idx", "assigned_to_employee_id", "status"),
        Index("tasks_assigned_by_idx", "assigned_by_employee_id"),
        Index("tasks_due_date_idx", "due_date"),
    )
