"""0081 permission period

Phase 4C - adds `period` to `permission_requests`: the one authoritative value
naming which of the four selectable options (1st/2nd Half x 1/2 Hours) a
requester picked. `duration_hours` (added before this phase, unchanged) stays on
the row as the hours the balance sum, the DB check constraint and the attendance
join all still read - it is derived from `period` at creation from this point
on, not chosen independently.

Additive and nullable: a permission filed before this phase recorded no half at
all, and none can be safely inferred from `duration_hours` alone (1 hour could
have been either half), so existing rows are left exactly as they are with
`period = NULL` rather than guessed at. Nothing here rewrites or backfills a
single existing value.

Revision ID: 0081_permission_period
Revises: 0080_permission_routed_project
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0081_permission_period"
down_revision: Union[str, None] = "0080_permission_routed_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PERMISSION_PERIOD = sa.Enum(
    "first_half_1h", "second_half_1h", "first_half_2h", "second_half_2h",
    name="permission_period",
)


def upgrade() -> None:
    _PERMISSION_PERIOD.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "permission_requests",
        sa.Column("period", _PERMISSION_PERIOD, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("permission_requests", "period")
    _PERMISSION_PERIOD.drop(op.get_bind(), checkfirst=True)
