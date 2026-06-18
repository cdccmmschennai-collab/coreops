"""0022 day_status office

Adds 'office' (worked from office) to the day_status enum so it can be chosen
as a Day Status on the daily work report. ALTER TYPE ... ADD VALUE is its own
migration (mirrors 0013): the new value must commit before any DML can
reference it. IF NOT EXISTS keeps it idempotent for databases that already
carry the value.

Revision ID: 0022_day_status_office
Revises: 0021_task_project
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0022_day_status_office"
down_revision: Union[str, None] = "0021_task_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE day_status ADD VALUE IF NOT EXISTS 'office'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    pass
