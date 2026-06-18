"""0021 task project link

Adds a nullable project_id to tasks so team leads can assign work scoped to a
project they lead. Existing PM-created tasks keep project_id NULL.

Revision ID: 0021_task_project
Revises: 0020_tasks
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0021_task_project"
down_revision: Union[str, None] = "0020_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("tasks_project_idx", "tasks", ["project_id"])


def downgrade() -> None:
    op.drop_index("tasks_project_idx", table_name="tasks")
    op.drop_column("tasks", "project_id")
