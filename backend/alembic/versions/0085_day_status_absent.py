"""0085 day_status absent

Adds 'absent' to the day_status enum, so an automatic report on a day a PM
marked Absent in Attendance can say ABSENT rather than LEAVE. Absent costs one
leave day (via the attendance row's leave_day_fraction, priced by
leave_balances.ledger) but stays a distinct status.

ALTER TYPE ... ADD VALUE is its own migration (mirrors 0049/0052): the new value
must commit before any DML can reference it. IF NOT EXISTS keeps it idempotent.
No existing row changes.

Revision ID: 0085_day_status_absent
Revises: 0084_leave_half_day_period
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0085_day_status_absent"
down_revision: Union[str, None] = "0084_leave_half_day_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE day_status ADD VALUE IF NOT EXISTS 'absent'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    pass
