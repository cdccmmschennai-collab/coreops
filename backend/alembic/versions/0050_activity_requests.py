"""0050 activity requests

Adds the `activity_requests` table backing the one-active-activity approval
workflow: when an employee already has an activity on their current work report
and tries to add another, an approval request is sent to the project's PM
instead of creating the activity outright.

A partial unique index enforces at most one PENDING request per employee.

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
        sa.Column("current_activity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("requested_project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_sub_activity_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="activity_requests_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], ondelete="RESTRICT",
            name="activity_requests_employee_fk",
        ),
        sa.ForeignKeyConstraint(
            ["current_activity_id"], ["work_report_tasks.id"], ondelete="SET NULL",
            name="activity_requests_current_activity_fk",
        ),
        sa.ForeignKeyConstraint(
            ["requested_project_id"], ["projects.id"], ondelete="CASCADE",
            name="activity_requests_project_fk",
        ),
        sa.ForeignKeyConstraint(
            ["requested_activity_id"], ["activity_master.id"], ondelete="RESTRICT",
            name="activity_requests_activity_fk",
        ),
        sa.ForeignKeyConstraint(
            ["requested_sub_activity_id"], ["activity_master.id"], ondelete="RESTRICT",
            name="activity_requests_sub_activity_fk",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"], ["users.id"], ondelete="SET NULL",
            name="activity_requests_approved_by_fk",
        ),
    )
    op.create_index("activity_requests_employee_idx", "activity_requests", ["employee_id"])
    op.create_index("activity_requests_status_idx", "activity_requests", ["status"])
    # At most one PENDING request per employee.
    op.create_index(
        "activity_requests_one_pending_uq",
        "activity_requests",
        ["employee_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("activity_requests_one_pending_uq", table_name="activity_requests")
    op.drop_index("activity_requests_status_idx", table_name="activity_requests")
    op.drop_index("activity_requests_employee_idx", table_name="activity_requests")
    op.drop_table("activity_requests")
