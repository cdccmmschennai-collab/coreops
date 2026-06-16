"""ActivityMaster ORM model — hierarchical Activity / Sub-Activity master data.

Replaces the flat `activity_types` table as the source of truth for activity
selection on work reports (`activity_types` is left in place, frozen/soft-
deactivated, for history and for `project_activities.activity_type_id`).

One self-referencing table covers both levels:
  parent_id IS NULL      -> Activity (top level)
  parent_id IS NOT NULL  -> Sub-Activity (leaf; carries the benchmark, if any)

The DB does not forbid a sub-activity from parenting another row — that is
enforced in the service layer (`create_sub_activity` requires the parent to be
level='activity'), a deliberate trade-off for keeping one table instead of two.

Benchmark types:
  NUMERIC      -> benchmark_value is a per-period quantity target (e.g. 250
                  tags/day). The *actual* value is not entered separately —
                  it's read straight off whichever of the work report task's
                  existing tags_count/docs_count/bom_count/spares_count
                  relevant_count_field points to, so the same number isn't
                  entered twice. relevant_count_field is therefore required
                  whenever benchmark_type='NUMERIC' (enforced below).
  TASK_BASED   -> no quantity target; must be completed within the allocated
                  duration (benchmark_period_days, doubling as
                  due_date - started_date on the work report task row).
                  Tracked by a single is_completed checkbox + system-managed
                  started_date/due_date/completed_date — no status dropdown,
                  no manual dates, no deficit/productivity calculation.
                  relevant_count_field is unused (NULL = "none").
  NULL         -> no benchmark tracked at all (pure logging line item, e.g.
                  LEAVE, TRAINING).
"""
import uuid

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin

LEVEL_ACTIVITY = "activity"
LEVEL_SUB_ACTIVITY = "sub_activity"
VALID_LEVELS = {LEVEL_ACTIVITY, LEVEL_SUB_ACTIVITY}

BENCHMARK_TYPE_NUMERIC = "NUMERIC"
BENCHMARK_TYPE_TASK_BASED = "TASK_BASED"
VALID_BENCHMARK_TYPES = {BENCHMARK_TYPE_NUMERIC, BENCHMARK_TYPE_TASK_BASED}

COUNT_FIELD_TAGS = "tags"
COUNT_FIELD_DOCS = "docs"
COUNT_FIELD_BOM = "bom"
COUNT_FIELD_SPARES = "spares"
VALID_COUNT_FIELDS = {COUNT_FIELD_TAGS, COUNT_FIELD_DOCS, COUNT_FIELD_BOM, COUNT_FIELD_SPARES}


class ActivityMaster(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "activity_master"

    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)

    benchmark_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    benchmark_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    benchmark_period_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    benchmark_unit_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    benchmark_remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which of tags_count/docs_count/bom_count/spares_count is this
    # sub-activity's benchmark source. Required when benchmark_type='NUMERIC';
    # unused (NULL = "none") otherwise.
    relevant_count_field: Mapped[str | None] = mapped_column(String(20), nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="activity_master_no_self_parent"),
        CheckConstraint("level IN ('activity', 'sub_activity')", name="activity_master_level_valid"),
        CheckConstraint(
            "benchmark_type IS NULL OR benchmark_type IN ('NUMERIC', 'TASK_BASED')",
            name="activity_master_benchmark_type_valid",
        ),
        CheckConstraint(
            "benchmark_type <> 'NUMERIC' OR benchmark_value IS NOT NULL",
            name="activity_master_numeric_requires_value",
        ),
        CheckConstraint(
            "relevant_count_field IS NULL OR relevant_count_field IN "
            "('tags', 'docs', 'bom', 'spares')",
            name="activity_master_relevant_count_field_valid",
        ),
        CheckConstraint(
            "benchmark_type <> 'NUMERIC' OR relevant_count_field IS NOT NULL",
            name="activity_master_numeric_requires_count_field",
        ),
        Index("activity_master_parent_idx", "parent_id"),
        Index("activity_master_active_idx", "is_active"),
        Index("activity_master_level_idx", "level"),
        Index(
            "activity_master_code_uq",
            "code",
            unique=True,
            postgresql_where=text("is_active = true AND code IS NOT NULL"),
        ),
    )
