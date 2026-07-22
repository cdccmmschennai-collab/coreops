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

Benchmark types (migration 0058 split the original two into five; the two
legacy values are still stored on historical rows and remain fully supported):

  NUMERIC_DAILY       -> benchmark_value is a per-day quantity target (e.g. 250
                         tags/day). The *actual* value is not entered
                         separately — it's read straight off whichever of the
                         work report task's existing tags_count/docs_count/
                         bom_count/spares_count/pages_count/records_count
                         relevant_count_field points to, so the same number
                         isn't entered twice. Pure daily production: no due
                         date, no completion checkbox, no carry-forward.
  TASK_STATUS_ONLY    -> no quantity target; must be completed within the
                         allocated duration (benchmark_period_days, doubling as
                         due_date - started_date on the work report task row).
                         Tracked by a single is_completed checkbox +
                         system-managed started_date/due_date/completed_date.
                         Carries forward until completed. No deficit/
                         productivity calculation. relevant_count_field unused.
  TASK_WITH_QUANTITY  -> both of the above: a due date + completion checkbox +
                         carry-forward AND a numeric target/actual/pending/
                         percentage. Exists because a task can legitimately
                         have a deadline *and* a measurable quantity (e.g. 500
                         pages/day within 1 day). Requires benchmark_value and
                         relevant_count_field.
  NULL                -> no benchmark tracked at all (pure logging line item,
                         e.g. LEAVE, TRAINING).

  NUMERIC             -> LEGACY. Identical behaviour to NUMERIC_DAILY.
  TASK_BASED          -> LEGACY. Identical behaviour to TASK_STATUS_ONLY.

Legacy values are deliberately NOT rewritten in place: historical rows keep the
value they were saved with (including work_report_tasks.benchmark_type_snapshot,
frozen at submit time), and every read path resolves behaviour through the
QUANTITY_BENCHMARK_TYPES / TASK_BENCHMARK_TYPES sets below rather than by
comparing against a single literal.
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

# Activity access mode (migration 0061). Who may select an Activity (and, by
# inheritance, its sub-activities) when recording a report:
#   COMMON     -> every active employee may use it (the pre-0061 behaviour;
#                 the migration backfills every existing activity to this).
#   RESTRICTED -> only employees with an active employee_activity_access row.
# VARCHAR(20) + CHECK, following the benchmark_type / activity_requests.status
# precedent — no native Postgres enum type to manage. access_type is only ever
# meaningful on a level='activity' row; sub-activities inherit their parent's.
ACCESS_TYPE_COMMON = "COMMON"
ACCESS_TYPE_RESTRICTED = "RESTRICTED"
VALID_ACCESS_TYPES = {ACCESS_TYPE_COMMON, ACCESS_TYPE_RESTRICTED}

# Legacy values — still stored on historical rows, never rewritten in place.
BENCHMARK_TYPE_NUMERIC = "NUMERIC"
BENCHMARK_TYPE_TASK_BASED = "TASK_BASED"
# Current values (migration 0058).
BENCHMARK_TYPE_NUMERIC_DAILY = "NUMERIC_DAILY"
BENCHMARK_TYPE_TASK_STATUS_ONLY = "TASK_STATUS_ONLY"
BENCHMARK_TYPE_TASK_WITH_QUANTITY = "TASK_WITH_QUANTITY"

LEGACY_BENCHMARK_TYPES = {BENCHMARK_TYPE_NUMERIC, BENCHMARK_TYPE_TASK_BASED}
VALID_BENCHMARK_TYPES = {
    BENCHMARK_TYPE_NUMERIC,
    BENCHMARK_TYPE_TASK_BASED,
    BENCHMARK_TYPE_NUMERIC_DAILY,
    BENCHMARK_TYPE_TASK_STATUS_ONLY,
    BENCHMARK_TYPE_TASK_WITH_QUANTITY,
}

# Behaviour is resolved through these two sets, never by comparing against a
# single literal — that is what keeps the legacy values working unchanged.
#
# QUANTITY: carries benchmark_value + relevant_count_field, and therefore a
# numeric target / actual / pending / percentage and an export subtotal.
QUANTITY_BENCHMARK_TYPES = {
    BENCHMARK_TYPE_NUMERIC,
    BENCHMARK_TYPE_NUMERIC_DAILY,
    BENCHMARK_TYPE_TASK_WITH_QUANTITY,
}
# TASK: carries a due date, a completion checkbox and carry-forward (a WorkItem).
TASK_BENCHMARK_TYPES = {
    BENCHMARK_TYPE_TASK_BASED,
    BENCHMARK_TYPE_TASK_STATUS_ONLY,
    BENCHMARK_TYPE_TASK_WITH_QUANTITY,
}
# The quantity modes that are NOT tasks: pure per-day production, which is what
# the daily benchmark ledger reports. Derived rather than written out, so the
# two source sets below can never drift into overlapping.
#
# This split matters: TASK_WITH_QUANTITY is a QUANTITY mode, but its numbers
# reach the benchmark export through the task/lumpsum query (which already
# renders a counted lumpsum's target/actual/pending), NOT through the daily
# ledger. Putting it in both would list the same work twice and double-count the
# cycle. The benchmark export relies on these two row sources staying disjoint.
DAILY_QUANTITY_BENCHMARK_TYPES = QUANTITY_BENCHMARK_TYPES - TASK_BENCHMARK_TYPES

COUNT_FIELD_TAGS = "tags"
COUNT_FIELD_DOCS = "docs"
COUNT_FIELD_BOM = "bom"
COUNT_FIELD_SPARES = "spares"
COUNT_FIELD_PAGES = "pages"
COUNT_FIELD_RECORDS = "records"
# Ordered: the four original units keep their positions, PAGES/RECORDS append.
# This order is the single source of truth for the report form's count inputs
# and the benchmark export's per-group unit columns.
COUNT_FIELDS = (
    COUNT_FIELD_TAGS,
    COUNT_FIELD_DOCS,
    COUNT_FIELD_BOM,
    COUNT_FIELD_SPARES,
    COUNT_FIELD_PAGES,
    COUNT_FIELD_RECORDS,
)
VALID_COUNT_FIELDS = set(COUNT_FIELDS)

# The ONE place a unit maps to its work_report_tasks column. Every actual-value
# lookup (Python getattr and SQL case()) derives from this, so adding a seventh
# unit never again means hunting down parallel condition blocks across services.
# Units are isolated by construction: each reads only its own column, so PAGES
# can never offset RECORDS and RECORDS can never offset DOCS.
COUNT_FIELD_BY_UNIT = {
    COUNT_FIELD_TAGS: "tags_count",
    COUNT_FIELD_DOCS: "docs_count",
    COUNT_FIELD_BOM: "bom_count",
    COUNT_FIELD_SPARES: "spares_count",
    COUNT_FIELD_PAGES: "pages_count",
    COUNT_FIELD_RECORDS: "records_count",
}


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
    # COMMON (default) / RESTRICTED — see the ACCESS_TYPE_* constants above.
    # Only meaningful on level='activity' rows; sub-activities inherit the parent.
    access_type: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=text("'COMMON'")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("parent_id IS NULL OR parent_id <> id", name="activity_master_no_self_parent"),
        CheckConstraint("level IN ('activity', 'sub_activity')", name="activity_master_level_valid"),
        CheckConstraint(
            "benchmark_type IS NULL OR benchmark_type IN "
            "('NUMERIC', 'TASK_BASED', 'NUMERIC_DAILY', 'TASK_STATUS_ONLY', "
            "'TASK_WITH_QUANTITY')",
            name="activity_master_benchmark_type_valid",
        ),
        # Every QUANTITY mode needs a target and a unit to read the actual from.
        # NOT IN yields NULL for a NULL benchmark_type, so a no-benchmark row
        # passes — same semantics as the original `<> 'NUMERIC'` form.
        CheckConstraint(
            "benchmark_type NOT IN ('NUMERIC', 'NUMERIC_DAILY', 'TASK_WITH_QUANTITY') "
            "OR benchmark_value IS NOT NULL",
            name="activity_master_numeric_requires_value",
        ),
        CheckConstraint(
            "relevant_count_field IS NULL OR relevant_count_field IN "
            "('tags', 'docs', 'bom', 'spares', 'pages', 'records')",
            name="activity_master_relevant_count_field_valid",
        ),
        CheckConstraint(
            "benchmark_type NOT IN ('NUMERIC', 'NUMERIC_DAILY', 'TASK_WITH_QUANTITY') "
            "OR relevant_count_field IS NOT NULL",
            name="activity_master_numeric_requires_count_field",
        ),
        CheckConstraint(
            "access_type IN ('COMMON', 'RESTRICTED')",
            name="activity_master_access_type_valid",
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
