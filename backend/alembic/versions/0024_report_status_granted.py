"""0024 report status 'granted'

Adds 'granted' to work_report_status — the editable state a report enters when a
reviewer grants an edit request (distinct from 'rejected', which means the
reviewer sent it back for changes). ADD VALUE is its own migration (mirrors
0013 / 0022) and idempotent via IF NOT EXISTS.

Revision ID: 0024_report_status_granted
Revises: 0023_report_edit_requested
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0024_report_status_granted"
down_revision: Union[str, None] = "0023_report_edit_requested"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE work_report_status ADD VALUE IF NOT EXISTS 'granted'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    pass
