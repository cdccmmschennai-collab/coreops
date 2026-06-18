"""0038 work report tasks due dates

TASK_BASED redesign: these activities start one day, run for the
sub-activity's allocated duration (activity_master.benchmark_period_days),
and may complete later — often after the report they were logged on is
already submitted/locked. Replaces the 3-state Status dropdown + manual
Completion Date with a single completion checkbox + system-managed dates.

  - task_status (pending/in_progress/completed) -> dropped
  - completion_date -> renamed completed_date (still user-driven via the new
    completion-toggle endpoint, but the column name now matches
    started_date/due_date for a consistent trio)
  - started_date -> added (= report.report_date, set server-side)
  - due_date -> added (= started_date + benchmark_period_days, server-side)
  - is_completed -> added (boolean; the checkbox)

started_date/due_date/is_completed/completed_date are never client-supplied
as raw dates — only is_completed is a real user input (the checkbox); dates
are always computed/stamped server-side.

Revision ID: 0038_work_report_tasks_due_dates
Revises: 0037_count_field_required
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038_work_report_tasks_due_dates"
down_revision: Union[str, None] = "0037_count_field_required"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "work_report_tasks_task_status_valid", "work_report_tasks", type_="check",
    )
    op.drop_column("work_report_tasks", "task_status")
    op.alter_column("work_report_tasks", "completion_date", new_column_name="completed_date")
    op.add_column("work_report_tasks", sa.Column("started_date", sa.Date(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("due_date", sa.Date(), nullable=True))
    op.add_column("work_report_tasks", sa.Column(
        "is_completed", sa.Boolean(), nullable=False, server_default=sa.text("false"),
    ))


def downgrade() -> None:
    op.drop_column("work_report_tasks", "is_completed")
    op.drop_column("work_report_tasks", "due_date")
    op.drop_column("work_report_tasks", "started_date")
    op.alter_column("work_report_tasks", "completed_date", new_column_name="completion_date")
    op.add_column("work_report_tasks", sa.Column("task_status", sa.String(20), nullable=True))
    op.create_check_constraint(
        "work_report_tasks_task_status_valid",
        "work_report_tasks",
        "task_status IS NULL OR task_status IN ('pending', 'in_progress', 'completed')",
    )
