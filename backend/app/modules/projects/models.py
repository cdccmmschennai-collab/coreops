"""Project + ProjectMember ORM models (V3_PROJECTS_PLAN.md §2-4).

Mirrors the Employees module conventions: UUID PK, audit timestamps,
soft-delete on the aggregate (projects), partial-unique natural key.
Membership is a plain join (no soft-delete); unassign = delete the row.
"""
import enum
import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class ProjectStatus(str, enum.Enum):
    planning = "planning"
    active = "active"
    on_hold = "on_hold"
    completed = "completed"
    archived = "archived"


class ProjectMemberRole(str, enum.Enum):
    # Active roles
    team_lead = "team_lead"
    contributor = "contributor"
    qc = "qc"
    # Deprecated — kept so SQLAlchemy can load pre-migration rows without crashing.
    # No member should have these values after migration 0013. Removed in 0018.
    lead = "lead"
    member = "member"


class Project(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"

    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    client: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        SAEnum(
            ProjectStatus,
            name="project_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=ProjectStatus.planning.value,
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_codes.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="projects_dates",
        ),
        Index(
            "projects_code_uq",
            "code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("projects_status_idx", "status", postgresql_where=text("deleted_at IS NULL")),
        Index("projects_job_code_idx", "job_code_id", postgresql_where=text("deleted_at IS NULL")),
    )


class ProjectMember(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[ProjectMemberRole] = mapped_column(
        SAEnum(
            ProjectMemberRole,
            name="project_member_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=ProjectMemberRole.contributor.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "employee_id", name="project_members_uq"),
        Index("project_members_project_idx", "project_id"),
        Index("project_members_employee_idx", "employee_id"),
    )


class ProjectManager(UUIDMixin, TimestampMixin, Base):
    """Explicit PM→project assignment. PMs have global read regardless of this table;
    this is used for routing notifications and for the assignment UI."""
    __tablename__ = "project_managers"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="project_managers_uq"),
        Index("project_managers_project_idx", "project_id"),
        Index("project_managers_user_idx", "user_id"),
    )
