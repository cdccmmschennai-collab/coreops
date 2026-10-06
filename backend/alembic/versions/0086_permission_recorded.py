"""0086 permission recorded

Adds ONE value, `recorded`, to the existing `permission_status` enum: the state
of a permission a project manager recorded directly from Daily Attendance Review.
Nobody requested it and nobody approved it, so it must not sit in `approved`.

It stays a row of `permission_requests` because that table IS the permission
ledger - `permissions/balance.py` derives the monthly allowance by summing it -
so a recorded permission consumes, restores on cancellation and resets monthly
exactly as an approved one does, with no second ledger. A `recorded` row never
enters the request workflow: it is never pending, never routed, never in a
review queue and never listed in All Requests.

Additive and backwards compatible, idempotent via `IF NOT EXISTS`, and - like
0082 - deliberately irreversible: PostgreSQL cannot drop an enum value, so
`downgrade` is a documented no-op.

NO DATA REWRITE. Rows a PM recorded before this migration (only ever on an
unreleased development branch) stay `approved`; the new value cannot be used in
the transaction that adds it anyway.

Revision ID: 0086_permission_recorded
Revises: 0085_day_status_absent
Create Date: 2026-10-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0086_permission_recorded"
down_revision: Union[str, None] = "0085_day_status_absent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE permission_status ADD VALUE IF NOT EXISTS 'recorded'")


def downgrade() -> None:
    # Intentionally a no-op - see the module docstring.
    pass
