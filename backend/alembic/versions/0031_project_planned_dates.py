"""0031 project planned completion date and change log

- Rename end_date → planned_completion_date on projects
- Add actual_completion_date (nullable date) to projects
- Update date-order check constraint
- Create project_planned_date_changes table for auditable change history

Revision ID: 0031_project_planned_dates
Revises: 0030_projects_end_date
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_project_planned_dates"
down_revision: Union[str, None] = "0030_projects_end_date"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename end_date → planned_completion_date
    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_dates")
    op.execute("ALTER TABLE projects RENAME COLUMN end_date TO planned_completion_date")
    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT projects_dates "
        "CHECK (planned_completion_date IS NULL OR start_date IS NULL "
        "OR planned_completion_date >= start_date)"
    )

    # Add actual_completion_date
    op.add_column("projects", sa.Column("actual_completion_date", sa.Date(), nullable=True))

    # Change-log table
    op.create_table(
        "project_planned_date_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_date", sa.Date(), nullable=True),
        sa.Column("new_date", sa.Date(), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="project_planned_date_changes_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE",
            name="project_planned_date_changes_project_fk"
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"], ["users.id"], ondelete="RESTRICT",
            name="project_planned_date_changes_user_fk"
        ),
    )
    op.create_index(
        "project_planned_date_changes_project_idx",
        "project_planned_date_changes",
        ["project_id"],
    )


def downgrade() -> None:
    op.drop_index("project_planned_date_changes_project_idx")
    op.drop_table("project_planned_date_changes")

    op.drop_column("projects", "actual_completion_date")

    op.execute("ALTER TABLE projects DROP CONSTRAINT IF EXISTS projects_dates")
    op.execute("ALTER TABLE projects RENAME COLUMN planned_completion_date TO end_date")
    op.execute(
        "ALTER TABLE projects ADD CONSTRAINT projects_dates "
        "CHECK (end_date IS NULL OR start_date IS NULL OR end_date >= start_date)"
    )
