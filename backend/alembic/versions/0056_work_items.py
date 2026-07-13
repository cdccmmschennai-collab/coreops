"""0056 work items (task continuation)

Introduces a persistent lifecycle record for TASK_BASED (lumpsum) activities so
one activity can span several daily reports while keeping a single, fixed
deadline and a single completion. Before this, each daily entry was an
independent work_report_tasks row with its own started/due date and completion,
so continuing an activity silently reset its deadline.

This migration is STRUCTURE ONLY and deliberately does NOT backfill:
  - create table work_items
  - add nullable work_report_tasks.work_item_id (FK -> work_items, ON DELETE
    RESTRICT so report history is never silently detached)
  - constraints + indexes

Every existing work_report_tasks row keeps work_item_id = NULL and therefore
retains its exact legacy row-based behaviour. Automatic backfill is intentionally
excluded: turning every historical unfinished TASK_BASED row into a work item
would surface long-dead rows as "open" continuation suggestions. Selective legacy
adoption is handled out-of-band by scripts/adopt_legacy_work_items.py (not run
here).

Revision ID: 0056_work_items
Revises: 0055_reconcile_project_members
Create Date: 2026-07-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0056_work_items"
down_revision: Union[str, None] = "0055_reconcile_project_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "work_items",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True,
            server_default=sa.text("gen_random_uuid()"), nullable=False,
        ),
        sa.Column("employee_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sub_activity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("started_on", sa.Date(), nullable=False),
        sa.Column("target_days", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("activity_name", sa.Text(), nullable=True),
        sa.Column("sub_activity_name", sa.Text(), nullable=True),
        sa.Column("project_code", sa.Text(), nullable=True),
        sa.Column("project_name", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["employee_id"], ["employees.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["sub_activity_id"], ["activity_master.id"], ondelete="RESTRICT"
        ),
        sa.CheckConstraint("target_days >= 1", name="work_items_target_days_positive"),
        sa.CheckConstraint("due_date >= started_on", name="work_items_due_after_start"),
        sa.CheckConstraint(
            "completed_on IS NULL OR completed_on >= started_on",
            name="work_items_completed_after_start",
        ),
    )
    op.create_index("work_items_employee_idx", "work_items", ["employee_id"])
    op.create_index(
        "work_items_employee_sub_idx", "work_items", ["employee_id", "sub_activity_id"]
    )
    op.create_index("work_items_due_date_idx", "work_items", ["due_date"])
    op.create_index(
        "work_items_open_idx",
        "work_items",
        ["employee_id", "due_date"],
        postgresql_where=sa.text("completed_on IS NULL"),
    )

    op.add_column(
        "work_report_tasks",
        sa.Column("work_item_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "work_report_tasks_work_item_fk",
        "work_report_tasks",
        "work_items",
        ["work_item_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "work_report_tasks_work_item_idx", "work_report_tasks", ["work_item_id"]
    )


def downgrade() -> None:
    op.drop_index("work_report_tasks_work_item_idx", table_name="work_report_tasks")
    op.drop_constraint(
        "work_report_tasks_work_item_fk", "work_report_tasks", type_="foreignkey"
    )
    op.drop_column("work_report_tasks", "work_item_id")

    op.drop_index("work_items_open_idx", table_name="work_items")
    op.drop_index("work_items_due_date_idx", table_name="work_items")
    op.drop_index("work_items_employee_sub_idx", table_name="work_items")
    op.drop_index("work_items_employee_idx", table_name="work_items")
    op.drop_table("work_items")
