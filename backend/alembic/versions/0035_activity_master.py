"""0035 activity master

Creates the activity_master table (hierarchical Activity -> Sub-Activity master
data, replacing free-text activity selection on work reports) and adds the
benchmark-tracking columns to work_report_tasks. Purely additive: no existing
table or column is touched.

The legacy `activity_types` table is left in place (still used by
project_activities.activity_type_id); it will be soft-deactivated row-by-row at
the data layer, not dropped here.

Revision ID: 0035_activity_master
Revises: 0034_project_activities
Create Date: 2026-06-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0035_activity_master"
down_revision: Union[str, None] = "0034_project_activities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_master",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Self-referencing hierarchy: NULL parent = Activity, set = Sub-Activity.
        sa.Column("parent_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        # Benchmark (sub-activity rows only; NULL/unused on Activity rows).
        sa.Column("benchmark_type", sa.String(20), nullable=True),
        sa.Column("benchmark_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("benchmark_period_days", sa.Integer(), nullable=True),
        sa.Column("benchmark_unit_note", sa.Text(), nullable=True),
        sa.Column("benchmark_remarks", sa.Text(), nullable=True),
        # UI hint only — which of the 4 existing work-report count fields this
        # sub-activity conventionally uses. Never enforced.
        sa.Column("relevant_count_field", sa.String(20), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("parent_id IS NULL OR parent_id <> id",
                           name="activity_master_no_self_parent"),
        sa.CheckConstraint("level IN ('activity', 'sub_activity')",
                           name="activity_master_level_valid"),
        sa.CheckConstraint(
            "benchmark_type IS NULL OR benchmark_type IN ('NUMERIC', 'TASK_BASED')",
            name="activity_master_benchmark_type_valid",
        ),
        sa.CheckConstraint(
            "benchmark_type <> 'NUMERIC' OR benchmark_value IS NOT NULL",
            name="activity_master_numeric_requires_value",
        ),
        sa.CheckConstraint(
            "relevant_count_field IS NULL OR relevant_count_field IN "
            "('tags', 'docs', 'bom', 'spares')",
            name="activity_master_relevant_count_field_valid",
        ),
    )
    op.create_index("activity_master_parent_idx", "activity_master", ["parent_id"])
    op.create_index("activity_master_active_idx", "activity_master", ["is_active"])
    op.create_index("activity_master_level_idx", "activity_master", ["level"])
    op.create_index(
        "activity_master_code_uq", "activity_master", ["code"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND code IS NOT NULL"),
    )

    # Benchmark-tracking columns on work_report_tasks — all nullable, purely
    # additive. tags_count/docs_count/bom_count/spares_count are untouched.
    op.add_column("work_report_tasks", sa.Column(
        "sub_activity_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("activity_master.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("work_report_tasks", sa.Column("sub_activity_name", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("activity_name", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("actual_count", sa.Integer(), nullable=True))
    op.add_column("work_report_tasks", sa.Column(
        "benchmark_value_snapshot", sa.Numeric(10, 2), nullable=True,
    ))
    op.add_column("work_report_tasks", sa.Column(
        "benchmark_period_days_snapshot", sa.Integer(), nullable=True,
    ))
    op.add_column("work_report_tasks", sa.Column(
        "benchmark_type_snapshot", sa.String(20), nullable=True,
    ))
    op.add_column("work_report_tasks", sa.Column("deficit", sa.Numeric(10, 2), nullable=True))
    op.add_column("work_report_tasks", sa.Column("productivity_pct", sa.Numeric(6, 2), nullable=True))
    op.add_column("work_report_tasks", sa.Column("task_status", sa.String(20), nullable=True))
    op.add_column("work_report_tasks", sa.Column("completion_date", sa.Date(), nullable=True))
    op.create_index(
        "work_report_tasks_sub_activity_idx", "work_report_tasks", ["sub_activity_id"],
    )
    op.create_check_constraint(
        "work_report_tasks_task_status_valid",
        "work_report_tasks",
        "task_status IS NULL OR task_status IN ('pending', 'in_progress', 'completed')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "work_report_tasks_task_status_valid", "work_report_tasks", type_="check",
    )
    op.drop_index("work_report_tasks_sub_activity_idx", table_name="work_report_tasks")
    for col in (
        "completion_date", "task_status", "productivity_pct", "deficit",
        "benchmark_type_snapshot", "benchmark_period_days_snapshot",
        "benchmark_value_snapshot", "actual_count", "activity_name",
        "sub_activity_name", "sub_activity_id",
    ):
        op.drop_column("work_report_tasks", col)

    op.drop_index("activity_master_code_uq", table_name="activity_master")
    op.drop_index("activity_master_level_idx", table_name="activity_master")
    op.drop_index("activity_master_active_idx", table_name="activity_master")
    op.drop_index("activity_master_parent_idx", table_name="activity_master")
    op.drop_table("activity_master")
