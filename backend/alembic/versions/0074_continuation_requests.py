"""0074 continuation requests

Adds the `continuation_requests` table - Lump-sum Activity Continuation
Approval (Phase 2). One row per continuation-approval request against a
specific WorkItem (app.modules.work_reports.models.WorkItem). See
app/modules/continuation_requests/models.py for the full column rationale.

Revision ID: 0074_continuation_requests
Revises: 0073_leave_routed_project
Create Date: 2026-08-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0074_continuation_requests"
down_revision: Union[str, None] = "0073_leave_routed_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "continuation_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("work_item_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("work_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sub_activity_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("original_report_date", sa.Date(), nullable=False),
        sa.Column("allowed_duration_days", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("continuation_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("employees.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decision_comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="continuation_requests_status_valid",
        ),
        sa.CheckConstraint(
            "continuation_date > due_date", name="continuation_requests_date_after_due"
        ),
    )
    op.create_index(
        "continuation_requests_employee_idx", "continuation_requests", ["employee_id"]
    )
    op.create_index(
        "continuation_requests_work_item_idx", "continuation_requests", ["work_item_id"]
    )
    op.create_index(
        "continuation_requests_project_idx", "continuation_requests", ["project_id"]
    )
    op.create_index(
        "continuation_requests_status_idx", "continuation_requests", ["status"]
    )
    op.create_index(
        "continuation_requests_one_pending_per_item_uq",
        "continuation_requests",
        ["work_item_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("continuation_requests_one_pending_per_item_uq", table_name="continuation_requests")
    op.drop_index("continuation_requests_status_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_project_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_work_item_idx", table_name="continuation_requests")
    op.drop_index("continuation_requests_employee_idx", table_name="continuation_requests")
    op.drop_table("continuation_requests")
