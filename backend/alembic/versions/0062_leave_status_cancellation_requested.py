"""0062 leave_status cancellation_requested

Adds 'cancellation_requested' to the leave_status enum: approved leave an
employee has asked to withdraw, awaiting a project manager's decision.

ALTER TYPE ... ADD VALUE is its own migration (mirrors 0049): the new value must
commit before any DML can reference it. IF NOT EXISTS keeps it idempotent, which
matters here — some local databases already carry the value from an earlier
migration attempt that was rolled back, and the revision must still record.

Revision ID: 0062_leave_cancellation_status
Revises: 0061_employee_activity_access
Create Date: 2026-07-28
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0062_leave_cancellation_status"
down_revision: Union[str, None] = "0061_employee_activity_access"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TYPE leave_status ADD VALUE IF NOT EXISTS 'cancellation_requested'"
    )


def downgrade() -> None:
    # PostgreSQL cannot remove an enum value once committed. Dropping it would
    # mean recreating the type and rewriting leave_requests.status, which is not
    # worth the risk on a live table — the unused value is inert.
    pass
