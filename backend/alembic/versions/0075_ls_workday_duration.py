"""0075 continuation requests - drop the calendar due-date check

A lump-sum activity's allowed duration is counted in WORK DAYS: the distinct
report dates the employee actually worked on that activity. Skipped calendar
days consume nothing, so the frozen calendar due_date no longer decides when
continuation approval is needed and `continuation_date > due_date` is no longer
an invariant.

Concrete counter-example the old CHECK would have rejected with a 500: a 3-day
lump-sum started on a Friday and worked Fri/Sat/Sun has spent all three work
days by Monday, while due_date skipped the weekend and sits on Tuesday - a
legitimate continuation request dated before its due_date.

Nothing else about the table changes; due_date stays as the frozen audit
snapshot of the item's calendar deadline.

Revision ID: 0075_ls_workday_duration
Revises: 0074_continuation_requests
Create Date: 2026-08-25
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0075_ls_workday_duration"
down_revision: Union[str, None] = "0074_continuation_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "continuation_requests_date_after_due",
        "continuation_requests",
        type_="check",
    )


def downgrade() -> None:
    # Rows created under the work-day rule may violate this, so the restore is
    # best-effort by design: it fails loudly rather than silently dropping data
    # if such a row exists.
    op.create_check_constraint(
        "continuation_requests_date_after_due",
        "continuation_requests",
        "continuation_date > due_date",
    )
