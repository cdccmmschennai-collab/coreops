"""Project Production Status ORM model (Phase 1 - data model only).

One row = one status update a Project Head or an Activity Lead recorded for a
(project, revision, activity) combination. The table is APPEND-ONLY: an update
never overwrites the previous row, so "01-Dec INPROGRESS TAG=180" and
"05-Dec CLOSED TAG=225" both survive and the trail stays auditable.

The current status of a (project, revision, activity) is therefore derived -
it is the newest row by created_at - not stored. Nothing in this module updates
or deletes a row; there is no PATCH/PUT/DELETE endpoint by design.

Shape follows the existing append-only history tables on this project
(ProjectPlannedDateChange / ProjectTagScopeRevision / DeliverableChange):
explicit UUID PK with a `gen_random_uuid()` server default, a single
`created_at`, no `updated_at` and no soft-delete, CASCADE to the project
(archiving a project is a soft delete, so archiving never touches history) and
RESTRICT on the author so a user with recorded history cannot be hard deleted.

Author identity: `created_by` is the real `users.id` of whoever pressed Save.
The role they held is deliberately NOT stored - the API resolves the person's
full name at read time (see service._attach_author_names), so "By" reads
"Santhosh Kumar", never "Activity Lead".

Activity link: `activity_id` points at `activity_master` (level='activity'),
the same table the per-activity staffing rows (`project_activity_members`) and
the Activity Lead relationship use. No duplicate activity record is created.
The service additionally requires the activity to be staffed on the project, so
only activities that are genuinely valid for that project can be recorded
against.

Status vocabulary: `in_progress` / `closed`. These are the exact string values
the existing `project_activities` module already uses for the same two business
states (see project_activities/models.py ACTIVITY_STATUS_*), so the system does
not grow a second, conflicting spelling of INPROGRESS/CLOSED. Stored as
VARCHAR(20) + CHECK rather than a native Postgres enum, matching the
activity_master.access_type / benchmark_type / projects.scope_type precedent:
widening the set later is an ALTER of one constraint.

Counts: TAG / DOC / SPARES / CRS are four independent columns, never a single
generic "count". Each is NOT NULL DEFAULT 0 with a non-negative CHECK, matching
how work_report_tasks stores its per-unit counts (tags_count / docs_count /
spares_count / ...) - an unused unit is 0 rather than NULL, so every SUM() and
comparison downstream stays arithmetic.
"""
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

# Same two literals `project_activities` already uses for these states.
PRODUCTION_STATUS_IN_PROGRESS = "in_progress"
PRODUCTION_STATUS_CLOSED = "closed"
VALID_PRODUCTION_STATUSES = {
    PRODUCTION_STATUS_IN_PROGRESS,
    PRODUCTION_STATUS_CLOSED,
}


class ProjectProductionStatus(Base):
    __tablename__ = "project_production_statuses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # User-entered document revision label ("REV-0", "R1", ...). Deliberately a
    # column on THIS table and not copied onto the project: a project carries
    # many revisions at once, and projects.tag_scope_revision is an unrelated
    # integer counter for tag-scope history.
    revision: Mapped[str] = mapped_column(Text, nullable=False)
    # activity_master row, level='activity' (enforced in the service).
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    tag_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    doc_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    spares_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    crs_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    completed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The Maintenance Plant this update belongs to (migration 0071). A POINTER
    # into existing plant master data - the same nullable FK shape
    # `work_report_tasks.maintenance_plant_id` already uses - so no plant code or
    # description is duplicated onto this row and no second plant source exists.
    #
    # Nullable on purpose, three ways: rows recorded before 0071 have none, a
    # project whose Planning Plant has no Maintenance Plants cannot offer one,
    # and choosing one is optional even when they exist. A missing plant is
    # never inferred from the project's Planning Plant.
    #
    # NOT part of the record's identity. "Current status" is still derived per
    # project + revision + activity; two updates that differ only by plant are
    # the same combination, and the newer one supersedes the older exactly as it
    # would have before this column existed.
    maintenance_plant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("maintenance_plants.id", ondelete="SET NULL"),
        nullable=True,
    )
    # The actual person, never the role. RESTRICT mirrors the other history
    # tables: an author with recorded updates cannot be hard deleted.
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'closed')",
            name="project_production_statuses_status_valid",
        ),
        # A revision label must be a real label - whitespace is not one.
        CheckConstraint(
            "btrim(revision) <> ''",
            name="project_production_statuses_revision_not_blank",
        ),
        # One constraint over all four units: they are independent values but
        # share a single rule, and four near-identical constraints would only
        # add noise.
        CheckConstraint(
            "tag_count >= 0 AND doc_count >= 0 AND spares_count >= 0 AND crs_count >= 0",
            name="project_production_statuses_counts_non_negative",
        ),
        # The two access paths the module actually has, and nothing else:
        #   1. latest / history for a project+revision+activity
        #   2. history for a project+activity across revisions
        # created_at DESC leads with the newest row, which is what "latest"
        # reads and what history renders first.
        Index(
            "project_production_statuses_project_revision_activity_idx",
            "project_id",
            "revision",
            "activity_id",
            text("created_at DESC"),
        ),
        Index(
            "project_production_statuses_project_activity_created_idx",
            "project_id",
            "activity_id",
            text("created_at DESC"),
        ),
        Index(
            "project_production_statuses_maintenance_plant_idx",
            "maintenance_plant_id",
        ),
    )
