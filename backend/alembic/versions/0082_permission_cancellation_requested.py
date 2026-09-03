"""0082 permission cancellation_requested

Phase 4E - adds ONE value, `cancellation_requested`, to the existing
`permission_status` enum so an approved permission an employee has asked to
withdraw has a state to sit in while an authorised reviewer decides.

WHY A MIGRATION IS NEEDED AT ALL
================================
`permission_requests.status` is a PostgreSQL ENUM type, not a text column, so a
new member of `PermissionStatus` has to exist in the database type before a row
can hold it. Nothing else changes: no new table, no new column, no constraint.
The alternative - a separate `permission_cancellation_requests` table - would be
a second cancellation framework beside Leave's, which represents exactly this
state on the request row itself. Reusing the existing representation is the
smaller change and keeps the two workflows readable as one.

ADDITIVE AND BACKWARDS COMPATIBLE
=================================
Adding an enum value rewrites nothing. Every existing row keeps the status it
has, every existing query keeps matching, and code that has not been updated
simply never produces the new value. `IF NOT EXISTS` makes the statement
idempotent, so a re-run (or a database already stamped by hand) is a no-op.

NOT REVERSIBLE, DELIBERATELY
============================
PostgreSQL cannot drop a value from an enum type. Undoing this would mean
rebuilding `permission_status` and rewriting the column, which on a database
that already holds a `cancellation_requested` row would have to either destroy
that row's state or refuse. `downgrade` is therefore a documented no-op: the
extra value is inert for any code that does not use it, which is precisely what
a downgraded application is.

Revision ID: 0082_permission_cancellation
Revises: 0081_permission_period
Create Date: 2026-09-03
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0082_permission_cancellation"
down_revision: Union[str, None] = "0081_permission_period"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 12+ allows ALTER TYPE ... ADD VALUE inside a transaction block
    # (which is how Alembic runs), with the single restriction that the new
    # value cannot be USED in that same transaction. Nothing here writes a row,
    # so that restriction does not apply.
    op.execute(
        "ALTER TYPE permission_status ADD VALUE IF NOT EXISTS 'cancellation_requested'"
    )


def downgrade() -> None:
    # Intentionally a no-op - see the module docstring.
    pass
