"""0006 daily report fields

Extends daily_work_reports and work_report_tasks with the fields that match
the company's existing Google Form daily report, enabling a full in-system
replacement. All new columns are nullable or carry a server_default so
existing rows are never broken.

Changes:
  - Two new ENUM types: day_status, work_location
  - daily_work_reports: day_status, location, remarks, query_text, well_head_no,
    pm_plant, and four integer counters (task_list_count, task_list_op_count,
    maintenance_item_count, maintenance_plan_count)
  - work_report_tasks: activity_type (nullable text), tags_count, docs_count,
    bom_count, spares_count (all NOT NULL, default 0)
  - work_report_tasks.minutes_spent: relax CHECK from >=1 to >=0, make nullable
    (the Google Form has no time field; time tracking is now optional)

Revision ID: 0006_daily_report_fields
Revises: 0005_work_reports
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_daily_report_fields"
down_revision: Union[str, None] = "0005_work_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. New ENUM types
    op.execute(
        "CREATE TYPE day_status AS ENUM "
        "('on_duty', 'half_day', 'on_leave', 'wfh', 'permission', 'comp_off')"
    )
    op.execute(
        "CREATE TYPE work_location AS ENUM "
        "('hyderabad', 'chennai', 'qatar')"
    )

    day_status_enum = postgresql.ENUM(
        "on_duty", "half_day", "on_leave", "wfh", "permission", "comp_off",
        name="day_status", create_type=False,
    )
    location_enum = postgresql.ENUM(
        "hyderabad", "chennai", "qatar",
        name="work_location", create_type=False,
    )

    # 2. New columns on daily_work_reports
    op.add_column("daily_work_reports", sa.Column("day_status", day_status_enum, nullable=True))
    op.add_column("daily_work_reports", sa.Column("location", location_enum, nullable=True))
    op.add_column("daily_work_reports", sa.Column("remarks", sa.Text(), nullable=True))
    op.add_column("daily_work_reports", sa.Column("query_text", sa.Text(), nullable=True))
    op.add_column("daily_work_reports", sa.Column("well_head_no", sa.Text(), nullable=True))
    op.add_column("daily_work_reports", sa.Column("pm_plant", sa.Text(), nullable=True))
    op.add_column(
        "daily_work_reports",
        sa.Column("task_list_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
    )
    op.add_column(
        "daily_work_reports",
        sa.Column("task_list_op_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
    )
    op.add_column(
        "daily_work_reports",
        sa.Column("maintenance_item_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
    )
    op.add_column(
        "daily_work_reports",
        sa.Column("maintenance_plan_count", sa.Integer(), nullable=True, server_default=sa.text("0")),
    )

    # 3. New columns on work_report_tasks
    op.add_column("work_report_tasks", sa.Column("activity_type", sa.Text(), nullable=True))
    op.add_column(
        "work_report_tasks",
        sa.Column("tags_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "work_report_tasks",
        sa.Column("docs_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "work_report_tasks",
        sa.Column("bom_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "work_report_tasks",
        sa.Column("spares_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    # 4. Relax minutes_spent: drop old CHECK (>=1), make nullable, add new CHECK (>=0 or NULL)
    op.drop_constraint("work_report_tasks_minutes_range", "work_report_tasks", type_="check")
    op.alter_column("work_report_tasks", "minutes_spent", nullable=True)
    op.create_check_constraint(
        "work_report_tasks_minutes_range",
        "work_report_tasks",
        "minutes_spent IS NULL OR (minutes_spent >= 0 AND minutes_spent <= 1440)",
    )


def downgrade() -> None:
    # Reverse minutes_spent change
    op.drop_constraint("work_report_tasks_minutes_range", "work_report_tasks", type_="check")
    op.alter_column("work_report_tasks", "minutes_spent", nullable=False)
    op.create_check_constraint(
        "work_report_tasks_minutes_range",
        "work_report_tasks",
        "minutes_spent >= 1 AND minutes_spent <= 1440",
    )

    # Drop task columns
    for col in ("spares_count", "bom_count", "docs_count", "tags_count", "activity_type"):
        op.drop_column("work_report_tasks", col)

    # Drop header columns
    for col in (
        "maintenance_plan_count", "maintenance_item_count", "task_list_op_count",
        "task_list_count", "pm_plant", "well_head_no", "query_text", "remarks",
        "location", "day_status",
    ):
        op.drop_column("daily_work_reports", col)

    op.execute("DROP TYPE IF EXISTS work_location")
    op.execute("DROP TYPE IF EXISTS day_status")
