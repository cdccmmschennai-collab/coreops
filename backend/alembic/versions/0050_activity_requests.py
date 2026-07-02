"""0050 activity requests (simplified)

A lightweight request an employee sends to a project's PM asking to be given
another activity. There is NO approval workflow inside the work report: the
request only carries the selected activity details and a pending/approved/
rejected status. The PM approves or rejects; coordination happens manually.

One table, no changes to any work-report tables.

Revision ID: 0050_activity_requests
Revises: 0049_attendance_comp_off
Create Date: 2026-07-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0050_activity_requests"
down_revision: Union[str, None] = "0049_attendance_comp_off"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sub_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tags_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("docs_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bom_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("spares_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("approved_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="activity_requests_pkey"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="activity_requests_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="RESTRICT",
            name="activity_requests_employee_fk",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE",
            name="activity_requests_project_fk",
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"], ["activity_master.id"], ondelete="RESTRICT",
            name="activity_requests_activity_fk",
        ),
        sa.ForeignKeyConstraint(
            ["sub_activity_id"], ["activity_master.id"], ondelete="RESTRICT",
            name="activity_requests_sub_activity_fk",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"], ["tasks.id"], ondelete="SET NULL",
            name="activity_requests_task_fk",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL",
            name="activity_requests_approved_by_fk",
        ),
    )
    op.create_index("activity_requests_employee_idx", "activity_requests", ["employee_id"])
    op.create_index("activity_requests_status_idx", "activity_requests", ["status"])


def downgrade() -> None:
    op.drop_index("activity_requests_status_idx", table_name="activity_requests")
    op.drop_index("activity_requests_employee_idx", table_name="activity_requests")
    op.drop_table("activity_requests")
