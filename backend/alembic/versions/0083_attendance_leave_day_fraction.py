"""0083 attendance leave_day_fraction

Adds `attendance_records.leave_day_fraction` - how much of one day was funded
from the LEAVE POOL. This is the fact CoreOps never recorded, and its absence is
the half-day leave accounting bug: `status` alone cannot say whether a `half_day`
row was an employee taking half a day off (0.5 of a leave day) or the office
closing at noon (0 leave days). Both were stored identically, so the ledger
counted neither and the KPI counted rows instead of days.

WHY A FRACTION AND NOT A NEW STATUS
===================================
`half_day` already means "the employee worked half the day", and the calendar,
the day popover, the Present KPI, the exports and the biometric review all switch
on it. Adding a `half_day_leave` member to `attendance_status` would force every
one of those to learn a new value to keep behaving as it does today. The missing
fact is not a new KIND of day - it is a QUANTITY the day never carried, so it is
stored as one and nothing that reads `status` changes meaning.

NULLABLE, AND NOTHING IS BACKFILLED
===================================
Exactly the rule migration 0081 followed. NULL means "not stated", and the
ledger reads a NULL row precisely as it read it before this migration existed:

    leave  -> 1 leave day        (unchanged)
    anything else -> 0           (unchanged)

So every one of the rows already in this database keeps the value it has always
contributed, and this migration cannot move a single balance. That matters here
because the `half_day` rows in production are NOT all the same thing: 29 of them
fall on 2026-08-14, a company-wide half day, and charging those employees half a
day of leave each is precisely the wrong answer. Nothing in the stored row
distinguishes them from a genuine half-day leave, so nothing here guesses - a
half-day leave is stated from now on, by the manager recording it.

THE CHECK CONSTRAINT
====================
Leave is transacted in halves and nothing else (0, 0.5, 1). The constraint is the
floor under the API validation rather than a restatement of it: a direct SQL
write, a fixture or a future endpoint cannot introduce 0.4 of a leave day.

Revision ID: 0083_attendance_leave_fraction
Revises: 0082_permission_cancellation
Create Date: 2026-09-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Max 32 chars: `alembic_version.version_num` is VARCHAR(32).
revision: str = "0083_attendance_leave_fraction"
down_revision: Union[str, None] = "0082_permission_cancellation"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_records",
        sa.Column("leave_day_fraction", sa.Numeric(3, 2), nullable=True),
    )
    op.create_check_constraint(
        "attendance_leave_fraction_half_steps",
        "attendance_records",
        "leave_day_fraction IS NULL OR ("
        " leave_day_fraction >= 0"
        " AND leave_day_fraction <= 1"
        " AND leave_day_fraction * 2 = trunc(leave_day_fraction * 2)"
        ")",
    )


def downgrade() -> None:
    op.drop_constraint(
        "attendance_leave_fraction_half_steps", "attendance_records", type_="check"
    )
    op.drop_column("attendance_records", "leave_day_fraction")
