"""Daily Work Report ORM models (mirrors employees/projects/attendance conventions).

A work report is a *header* — one row per (employee, report_date) — composed of one
or more *task lines* (work_report_tasks), each attributing minutes to a project.

Operational records: no soft-delete. Only `draft` reports are hard-deletable (enforced
in the service layer); submitted/approved/rejected reports are retained. `total_minutes`
on the header is derived (sum of task minutes), set server-side like attendance minutes.

Relationships follow the codebase convention: FK columns with ondelete semantics, no
ORM `relationship()` objects (mirrors Project / ProjectMember). Task lines are owned by
the header via ON DELETE CASCADE; project/employee references use RESTRICT.
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
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class WorkReportStatus(str, enum.Enum):
    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"


class DailyWorkReport(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "daily_work_reports"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[WorkReportStatus] = mapped_column(
        SAEnum(
            WorkReportStatus,
            name="work_report_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=WorkReportStatus.draft.value,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_minutes: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("employee_id", "report_date", name="work_reports_emp_date_uq"),
        CheckConstraint(
            "total_minutes >= 0 AND total_minutes <= 1440", name="work_reports_total_minutes_range"
        ),
        Index("work_reports_employee_idx", "employee_id", "report_date"),
        Index("work_reports_status_idx", "status"),
        Index("work_reports_date_idx", "report_date"),
    )


class WorkReportTask(UUIDMixin, Base):
    __tablename__ = "work_report_tasks"

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("daily_work_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    minutes_spent: Mapped[int] = mapped_column(Integer, nullable=False)
    # Lines are replaced wholesale on edit; only creation time is tracked (no updated_at).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "minutes_spent >= 1 AND minutes_spent <= 1440", name="work_report_tasks_minutes_range"
        ),
        Index("work_report_tasks_report_idx", "report_id"),
        Index("work_report_tasks_project_idx", "project_id"),
    )
