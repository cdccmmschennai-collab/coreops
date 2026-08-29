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
    Integer,
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


# Project scope classification (migration 0064). Does this project take part in
# Project Tag Scope functionality at all?
#   NONE      -> not a tag-based project (TOOL DEVELOPMENT, TRAINING, INTERNAL
#                DEVELOPMENT, ...). Behaves exactly as every project does today.
#                Every pre-0064 project is backfilled to this.
#   TAG_BASED -> participates in Project Tag Scope. Later phases hang estimated
#                tags, revisions and progress off this classification; in this
#                phase the value is purely a label and changes no behaviour.
# VARCHAR(20) + CHECK rather than a native Postgres enum, following the
# activity_master.access_type / benchmark_type / benchmark_exception_code
# precedent — widening the set later is an ALTER of one constraint.
SCOPE_TYPE_NONE = "NONE"
SCOPE_TYPE_TAG_BASED = "TAG_BASED"
VALID_SCOPE_TYPES = {SCOPE_TYPE_NONE, SCOPE_TYPE_TAG_BASED}

# Tag scope status (migration 0065). How settled is the estimated tag count?
#   PROVISIONAL -> initial planning estimate, expected to move.
#   BASELINED   -> FMTL / scope-discovery has established the working scope.
# Deliberately no FINALIZED: scope can still be revised later when tags surface
# from new documents, drawings, references or vendor information.
# NULL means "no estimate exists yet" — it is not a status, and is the only
# state a project can be in before its first revision.
TAG_SCOPE_STATUS_PROVISIONAL = "PROVISIONAL"
TAG_SCOPE_STATUS_BASELINED = "BASELINED"
VALID_TAG_SCOPE_STATUSES = {TAG_SCOPE_STATUS_PROVISIONAL, TAG_SCOPE_STATUS_BASELINED}


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

    # Nullable (migration 0078): a project may begin work before a permanent
    # code is assigned (e.g. a Tag Estimation engagement). Creating/editing a
    # project through the normal API still requires a code (ProjectCreate/
    # ProjectUpdate) — this only allows such a row to exist and be read back.
    # The employee-entered fallback used on work reports for a code-less
    # project lives on work_report_tasks.project_code, never here.
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    # NONE (default) / TAG_BASED — see the SCOPE_TYPE_* constants above. Purely a
    # classification in this phase: no tag counts, no validation, no calculation
    # reads it yet.
    scope_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'NONE'")
    )
    # --- Current tag scope (migration 0065) -------------------------------
    # Denormalised "latest state" so the project page needs no aggregate over
    # the revision history. The authoritative trail is
    # project_tag_scope_revisions; these columns are what the newest revision
    # left behind.
    #
    # NULL count = "scope not established yet", which is NOT the same business
    # fact as 0 (0 is rejected outright). A TAG_BASED project legitimately sits
    # at NULL until someone establishes the estimate.
    estimated_tag_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PROVISIONAL / BASELINED, or NULL while no estimate exists.
    tag_scope_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 0 before the first estimate, then 1, 2, 3 ... one per recorded change.
    tag_scope_revision: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    tag_scope_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Plain user-id column with no FK, matching created_by / updated_by on this
    # same table (the history table's changed_by carries the FK, mirroring
    # ProjectPlannedDateChange).
    tag_scope_updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "planned_completion_date IS NULL OR start_date IS NULL OR planned_completion_date >= start_date",
            name="projects_dates",
        ),
        CheckConstraint(
            "scope_type IN ('NONE', 'TAG_BASED')",
            name="projects_scope_type_valid",
        ),
        # Unknown scope is NULL, never 0 — 0 and "not established" are different
        # business facts, so a stored count must be a real positive estimate.
        CheckConstraint(
            "estimated_tag_count IS NULL OR estimated_tag_count > 0",
            name="projects_estimated_tag_count_positive",
        ),
        CheckConstraint(
            "tag_scope_status IS NULL OR tag_scope_status IN ('PROVISIONAL', 'BASELINED')",
            name="projects_tag_scope_status_valid",
        ),
        CheckConstraint(
            "tag_scope_revision >= 0",
            name="projects_tag_scope_revision_non_negative",
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


class ProjectTagScopeRevision(Base):
    """Append-only trail of every tag-scope change on a project (migration 0065).

    One row per revision. Revision 1 is the first estimate (previous_* are NULL);
    each later row carries what the value was and what it became, plus the
    mandatory reason. Never updated or deleted — the projects.* columns hold the
    current state, this holds how it got there.

    Deliberately shaped like ProjectPlannedDateChange (the existing "what
    changed, why, by whom" log on this same table): explicit UUID PK, CASCADE to
    the project, RESTRICT on the user so an actor with history cannot be hard
    deleted. Archiving a project is a soft delete (deleted_at), so archiving
    never touches these rows and never orphans them.
    """
    __tablename__ = "project_tag_scope_revisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # 1-based, dense, unique within the project (see the constraint below).
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    # NULL on revision 1 — there was no previous scope.
    previous_estimated_tag_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_estimated_tag_count: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    changed_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        # Revision numbers restart per project — never globally unique.
        UniqueConstraint("project_id", "revision", name="project_tag_scope_revisions_uq"),
        CheckConstraint(
            "revision >= 1", name="project_tag_scope_revisions_revision_positive"
        ),
        CheckConstraint(
            "new_estimated_tag_count > 0",
            name="project_tag_scope_revisions_new_count_positive",
        ),
        CheckConstraint(
            "previous_estimated_tag_count IS NULL OR previous_estimated_tag_count > 0",
            name="project_tag_scope_revisions_prev_count_positive",
        ),
        CheckConstraint(
            "new_status IN ('PROVISIONAL', 'BASELINED')",
            name="project_tag_scope_revisions_new_status_valid",
        ),
        CheckConstraint(
            "previous_status IS NULL OR previous_status IN ('PROVISIONAL', 'BASELINED')",
            name="project_tag_scope_revisions_prev_status_valid",
        ),
        Index("project_tag_scope_revisions_project_idx", "project_id", "revision"),
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
