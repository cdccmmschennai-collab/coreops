"""Project + ProjectMember ORM models (V3_PROJECTS_PLAN.md §2-4).

Mirrors the Employees module conventions: UUID PK, audit timestamps,
soft-delete on the aggregate (projects), partial-unique natural key.
Membership is a plain join (no soft-delete); unassign = delete the row.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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
    planned_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    job_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("job_codes.id", ondelete="SET NULL"), nullable=True
    )
    # The Planning Plant this project belongs to (project master link). The
    # project carries the Planning Plant directly; Maintenance Plants hang off
    # the Planning Plant (maintenance_plants.planning_plant_id) and are picked
    # at usage time once that master data is loaded — not stored on the project.
    planning_plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("planning_plants.id", ondelete="SET NULL"), nullable=True
    )
    # Legacy direct Maintenance Plant link (pre-master-data). Retained for
    # backward compatibility; new project master rows leave this null and use
    # planning_plant_id instead. Its Planning Plant code/description are joined
    # in by the service (_attach_maintenance_plants), same pattern as job_code.
    maintenance_plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("maintenance_plants.id", ondelete="SET NULL"), nullable=True
    )
    # Phase 2 - Head ownership. One employee owns the project: report reviewer
    # (with the PM) and primary notification-routing target. Nullable; projects
    # start with no Head. Assigned via PUT /projects/{id}/head.
    head_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "planned_completion_date IS NULL OR start_date IS NULL OR planned_completion_date >= start_date",
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
        Index("projects_planning_plant_idx", "planning_plant_id"),
        Index("projects_maintenance_plant_idx", "maintenance_plant_id"),
        Index("projects_head_employee_idx", "head_employee_id"),
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


class ActivityMemberRole(str, enum.Enum):
    """Base staffing role on a project activity. QC is NOT a role value here -
    it is an additive `is_qc` flag on the assignment (spec SS4.1)."""
    lead = "lead"
    contributor = "contributor"


class ProjectActivityMember(UUIDMixin, TimestampMixin, Base):
    """Per-activity staffing (Phase 3). Assigns an employee to one activity of a
    project with a base role (lead|contributor) plus an additive QC flag. Exactly
    one Lead per activity is enforced by the partial-unique index below (and by
    the service layer, which also validates activity_id -> level='activity')."""
    __tablename__ = "project_activity_members"

    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # Activity node in activity_master; service enforces it is a level='activity' row.
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    role: Mapped[ActivityMemberRole] = mapped_column(
        SAEnum(
            ActivityMemberRole,
            name="project_activity_member_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # Additive QC responsibility; may be true on a lead or a contributor.
    is_qc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "project_id", "activity_id", "employee_id", name="project_activity_members_uq"
        ),
        # At most one Lead per (project, activity).
        Index(
            "project_activity_members_one_lead_uq",
            "project_id",
            "activity_id",
            unique=True,
            postgresql_where=text("role = 'lead'"),
        ),
        Index("project_activity_members_project_idx", "project_id"),
        Index("project_activity_members_activity_idx", "activity_id"),
        Index("project_activity_members_employee_idx", "employee_id"),
        Index("project_activity_members_project_activity_idx", "project_id", "activity_id"),
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


class ProjectPlannedDateChange(Base):
    """Append-only log of every planned_completion_date change on a project."""
    __tablename__ = "project_planned_date_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    old_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    new_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("project_planned_date_changes_project_idx", "project_id"),
    )


# Event type string constants — used as values for ProjectTimelineEvent.event_type
class TimelineEventType:
    PROJECT_CREATED = "project_created"
    PLANNED_DATE_CHANGED = "planned_date_changed"
    MEMBER_ADDED = "member_added"
    MEMBER_REMOVED = "member_removed"
    HEAD_ASSIGNED = "head_assigned"   # Phase 2 — first Head set on the project
    HEAD_CHANGED = "head_changed"     # Phase 2 — Head replaced or cleared
    # Phase 3 — per-activity staffing changes (only meaningful ones).
    ACTIVITY_LEAD_ASSIGNED = "activity_lead_assigned"
    ACTIVITY_CONTRIBUTOR_ADDED = "activity_contributor_added"
    ACTIVITY_MEMBER_REMOVED = "activity_member_removed"
    ACTIVITY_QC_ASSIGNED = "activity_qc_assigned"
    ACTIVITY_QC_REMOVED = "activity_qc_removed"
    SUBMISSION_CREATED = "submission_created"   # emitted by Phase C
    SUBMISSION_UPDATED = "submission_updated"   # emitted by Phase C


class ProjectTimelineEvent(Base):
    """Append-only log of structural project changes. Never updated or deleted."""
    __tablename__ = "project_timeline_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("project_timeline_events_project_idx", "project_id", "created_at"),
    )
