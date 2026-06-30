"""0049 attendance comp_off

Adds 'comp_off' (compensatory day off, granted by the manager for worked
overtime) to the attendance_status enum so it can be recorded as an attendance
status. ALTER TYPE ... ADD VALUE is its own migration (mirrors 0022): the new
value must commit before any DML can reference it. IF NOT EXISTS keeps it
idempotent for databases that already carry the value.

Revision ID: 0049_attendance_comp_off
Revises: 0048_day_status_taxonomy
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0049_attendance_comp_off"
down_revision: Union[str, None] = "0048_day_status_taxonomy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE attendance_status ADD VALUE IF NOT EXISTS 'comp_off'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    pass
