"""0020 tasks

Adds the tasks table for global task assignments (Phase 9A MVP).
One row per task with a single assignee; operational log (no soft-delete).

Revision ID: 0020_tasks
Revises: 0019_audit_logs
Create Date: 2026-06-09
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_tasks"
down_revision: Union[str, None] = "0019_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

task_status = postgresql.ENUM(
    "open",
    "in_progress",
    "completed",
    "cancelled",
    name="task_status",
    create_type=False,
)
task_priority = postgresql.ENUM(
    "low",
    "medium",
    "high",
    name="task_priority",
    create_type=False,
)


def upgrade() -> None:
    op.execute(
        "CREATE TYPE task_status AS ENUM ('open', 'in_progress', 'completed', 'cancelled')"
    )
    op.execute("CREATE TYPE task_priority AS ENUM ('low', 'medium', 'high')")

    op.create_table(
        "tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "assigned_to_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "assigned_by_employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            task_status,
            nullable=False,
            server_default="open",
        ),
        sa.Column(
            "priority",
            task_priority,
            nullable=False,
            server_default="medium",
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("tasks_assigned_to_idx", "tasks", ["assigned_to_employee_id", "status"])
    op.create_index("tasks_assigned_by_idx", "tasks", ["assigned_by_employee_id"])
    op.create_index("tasks_due_date_idx", "tasks", ["due_date"])


def downgrade() -> None:
    op.drop_index("tasks_due_date_idx", table_name="tasks")
    op.drop_index("tasks_assigned_by_idx", table_name="tasks")
    op.drop_index("tasks_assigned_to_idx", table_name="tasks")
    op.drop_table("tasks")
    op.execute("DROP TYPE task_priority")
    op.execute("DROP TYPE task_status")
