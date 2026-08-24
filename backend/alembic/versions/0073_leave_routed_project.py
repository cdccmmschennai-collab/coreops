"""0073 leave routed project

Adds `routed_project_id` to `leave_requests` — Phase 1 of leave-approval
routing to Project Head. Nullable, SET NULL when the project is deleted.

This is the historical PROJECT the employee's previous working day's Daily
Work Report shows them on — resolved once at creation (leave/routing.py) and
never rewritten. It is NOT a frozen approver: whether a Head reviews this
request, and which Head, is always resolved from the project's CURRENT
head_employee_id at read/notify/approve time (app.core.authz), so a Head
reassignment after the request was filed is honoured. NULL means no single
project could be determined and the request falls back to the existing PM
approval flow, exactly as before this migration.

Revision ID: 0073_leave_routed_project
Revises: 0072_prod_status_activity
Create Date: 2026-08-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0073_leave_routed_project"
down_revision: Union[str, None] = "0072_prod_status_activity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("leave_requests", sa.Column(
        "routed_project_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index(
        "leave_routed_project_idx", "leave_requests", ["routed_project_id"],
    )


def downgrade() -> None:
    op.drop_index("leave_routed_project_idx", table_name="leave_requests")
    op.drop_column("leave_requests", "routed_project_id")
