"""0084 leave half_day_period

Adds `leave_requests.half_day_period` - WHICH HALF of a single working day a
leave request covers, when it covers only half of one.

WHY A COLUMN ON THE REQUEST AND NOTHING ELSE
============================================
CoreOps could already RECORD a half-day leave - migration 0083 put
`leave_day_fraction` on `attendance_records`, and `leave_balances.ledger` prices
a `half_day` row carrying 0.5 at exactly half a leave day. What it could not do
was REQUEST one: a leave request had no way to say "half of this day", so a
half-day leave could only ever be typed straight onto the attendance record by a
project manager, skipping routing, review, notification and the audit trail that
every other absence goes through.

This is that missing fact and only that fact. It carries the half through the
EXISTING workflow (`leave/service.py` -> `leave/routing.py` -> the existing
approver -> the existing notifications -> `leave/effects.py`), which then writes
the very row 0083 already knows how to price. No second approval path, no second
routing rule, no new `attendance_status` member, and no new pricing rule.

NULLABLE, AND NOTHING IS BACKFILLED
===================================
The same rule migrations 0081 and 0083 followed. NULL means "not a half-day
request", which is precisely what every request already in this table is, so
every existing row keeps costing exactly what it costs today and no balance can
move. A stated value is only ever written by a requester choosing one.

THE CHECK CONSTRAINT
====================
A half day is half of ONE day. `start_date = end_date` is the floor under the
API validation rather than a restatement of it: a fixture, a script or a future
endpoint must not be able to create a "half day" spanning a fortnight, because
`apply_leave_approved` would then owe half a day to each of its working days and
"both variants consume exactly 0.5" would stop being true.

Revision ID: 0084_leave_half_day_period
Revises: 0083_attendance_leave_fraction
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Max 32 chars: `alembic_version.version_num` is VARCHAR(32).
revision: str = "0084_leave_half_day_period"
down_revision: Union[str, None] = "0083_attendance_leave_fraction"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HALF_DAY_PERIOD = sa.Enum(
    "first_half", "second_half", name="leave_half_day_period"
)


def upgrade() -> None:
    _HALF_DAY_PERIOD.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "leave_requests",
        sa.Column("half_day_period", _HALF_DAY_PERIOD, nullable=True),
    )
    op.create_check_constraint(
        "leave_half_day_is_one_day",
        "leave_requests",
        "half_day_period IS NULL OR start_date = end_date",
    )


def downgrade() -> None:
    op.drop_constraint("leave_half_day_is_one_day", "leave_requests", type_="check")
    op.drop_column("leave_requests", "half_day_period")
    _HALF_DAY_PERIOD.drop(op.get_bind(), checkfirst=True)
