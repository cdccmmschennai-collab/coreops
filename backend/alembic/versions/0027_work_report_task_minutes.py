"""0027 work_report_tasks → task_minutes_spent

Adds work_report_tasks.task_minutes_spent so a row can record task-based hours
separately from the project-activity hours (minutes_spent). Both add to the
report total. Idempotent for safety on the shared dev DB.

Revision ID: 0027_work_report_task_minutes
Revises: 0026_work_report_task_link
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0027_work_report_task_minutes"
down_revision: Union[str, None] = "0026_work_report_task_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE work_report_tasks ADD COLUMN IF NOT EXISTS task_minutes_spent integer"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE work_report_tasks DROP COLUMN IF EXISTS task_minutes_spent")
