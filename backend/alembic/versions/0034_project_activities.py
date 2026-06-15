"""0034 project activities

Creates the project_activities table for Phase B — Deliverable Activity Tracker.
Each row is one line item in a project's deliverable plan (replaces Excel Sheet 1).

Revision ID: 0034_project_activities
Revises: 0033_project_submissions
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0034_project_activities"
down_revision: Union[str, None] = "0033_project_submissions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_activities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # Project link
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        # Activity type (global master, optional — PM may leave blank)
        sa.Column("activity_type_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("activity_types.id", ondelete="SET NULL"), nullable=True),
        sa.Column("activity_type_name", sa.Text(), nullable=True),   # snapshot
        # Core fields
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        # Assignee (single employee; nullable)
        sa.Column("assigned_to_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_to_name", sa.Text(), nullable=True),     # snapshot
        # Dates
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("closed_date", sa.Date(), nullable=True),
        # Notes
        sa.Column("remarks", sa.Text(), nullable=True),
        # Manual ordering within a project
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        # Audit
        sa.Column("created_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        # Constraints
        sa.CheckConstraint(
            "status IN ('open', 'in_progress', 'closed')",
            name="project_activities_status_valid",
        ),
    )
    op.create_index("project_activities_project_idx", "project_activities", ["project_id"])
    op.create_index("project_activities_status_idx",  "project_activities", ["status"])
    op.create_index("project_activities_assignee_idx","project_activities", ["assigned_to_id"])


def downgrade() -> None:
    op.drop_index("project_activities_assignee_idx", table_name="project_activities")
    op.drop_index("project_activities_status_idx",   table_name="project_activities")
    op.drop_index("project_activities_project_idx",  table_name="project_activities")
    op.drop_table("project_activities")
