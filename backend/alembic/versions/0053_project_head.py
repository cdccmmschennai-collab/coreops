"""0053 project head

Adds a nullable Head owner to each project (Phase 2 - Head ownership).

One employee per project may be designated Head: the project owner, a report
reviewer alongside the PM, and the primary notification-routing target. The
column is nullable (projects start with no Head) and SET NULL when the linked
employee is deleted. Additive and backward-compatible; the assignment API and
behavior (review/visibility/routing) land in later Phase-2 tasks.

Revision ID: 0053_project_head
Revises: 0052_day_status_half_day
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0053_project_head"
down_revision: Union[str, None] = "0052_day_status_half_day"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column(
        "head_employee_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index(
        "projects_head_employee_idx", "projects", ["head_employee_id"],
    )


def downgrade() -> None:
    op.drop_index("projects_head_employee_idx", table_name="projects")
    op.drop_column("projects", "head_employee_id")
