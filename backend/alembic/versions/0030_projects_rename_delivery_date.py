"""0030 projects rename target_delivery_date to end_date

The projects table was created on another branch with target_delivery_date
instead of end_date. This migration renames the column to match the ORM model
and also drops the now-stale actual_completion_date column that is unused by
the application.

Revision ID: 0030_projects_rename_delivery_date
Revises: 0029_project_deliverables
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_projects_end_date"
down_revision: Union[str, None] = "0029_project_deliverables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop old check constraint that references target_delivery_date
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_dates")
    # Rename column
    op.execute(
        "ALTER TABLE projects RENAME COLUMN target_delivery_date TO end_date"
    )
    # Recreate constraint with new column name
    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT projects_dates "
        "CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)"
    )
    # Drop unused column (no ORM field references it)
    op.execute(
        "ALTER TABLE projects DROP COLUMN IF EXISTS actual_completion_date"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_dates")
    op.execute("ALTER TABLE projects ADD COLUMN IF NOT EXISTS actual_completion_date date")
    op.execute("ALTER TABLE projects RENAME COLUMN end_date TO target_delivery_date")
    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT projects_dates "
        "CHECK (target_delivery_date IS NULL OR start_date IS NULL "
        "OR target_delivery_date >= start_date)"
    )
