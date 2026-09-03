"""0080 permission routed project

Phase 4B - adds `routed_project_id` to `permission_requests`, the same column
`leave_requests` got in 0073 and for the same reason: the historical project
`leave/routing.py::resolve_routed_project` establishes from the employee's Daily
Work Report evidence, resolved once at creation and never rewritten. Who
currently Heads that project (and therefore who reviews) is always resolved
live via `app.core.authz`, not stored here. NULL means no single project could
be determined and the request falls back to the existing PM /
`reporting_pm_id` approval flow, exactly as before this migration.

Revision ID: 0080_permission_routed_project
Revises: 0079_report_origin
Create Date: 2026-09-02
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0080_permission_routed_project"
down_revision: Union[str, None] = "0079_report_origin"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("permission_requests", sa.Column(
        "routed_project_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index(
        "permission_routed_project_idx", "permission_requests", ["routed_project_id"],
    )


def downgrade() -> None:
    op.drop_index("permission_routed_project_idx", table_name="permission_requests")
    op.drop_column("permission_requests", "routed_project_id")
