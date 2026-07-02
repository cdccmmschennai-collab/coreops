"""0052 day_status half_day

Adds 'half_day' to the day_status enum. A half day is a working day (the
employee still logs activities and a location), but every NUMERIC benchmark
target for that day is halved - benchmark 100 -> 50 - when deficit/productivity
and the daily benchmark ledger are computed.

ALTER TYPE ... ADD VALUE is its own migration (mirrors 0049): the new value must
commit before any DML can reference it. IF NOT EXISTS keeps it idempotent for
databases that already carry the value.

Revision ID: 0052_day_status_half_day
Revises: 0051_activity_request_report_id
Create Date: 2026-07-02
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0052_day_status_half_day"
down_revision: Union[str, None] = "0051_activity_request_report_id"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE day_status ADD VALUE IF NOT EXISTS 'half_day'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    pass
