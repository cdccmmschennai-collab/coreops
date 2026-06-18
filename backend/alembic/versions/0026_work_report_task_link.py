"""0026 work_report_tasks → task link

Adds work_report_tasks.task_id (FK tasks.id, SET NULL) + task_title snapshot so a
report activity can log work against an assigned Task. Idempotent (ADD COLUMN IF
NOT EXISTS): this shared dev DB may already carry the columns from an earlier
branch; a fresh DB gets them created here.

Revision ID: 0026_work_report_task_link
Revises: 0025_report_edit_request_note
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0026_work_report_task_link"
down_revision: Union[str, None] = "0025_report_edit_request_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE work_report_tasks "
        "ADD COLUMN IF NOT EXISTS task_id uuid REFERENCES tasks(id) ON DELETE SET NULL"
    )
    op.execute(
        "ALTER TABLE work_report_tasks ADD COLUMN IF NOT EXISTS task_title text"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE work_report_tasks DROP COLUMN IF EXISTS task_title")
    op.execute("ALTER TABLE work_report_tasks DROP COLUMN IF EXISTS task_id")
