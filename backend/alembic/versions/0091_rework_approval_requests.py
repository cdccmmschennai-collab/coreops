"""0091 rework approval requests

Rework Activity Approval - Phase 2 (request lifecycle).

    rework_approval_requests            one row per APPROVAL CYCLE
    work_report_tasks.rework_request_id the cycle that currently governs a row

A request is raised at SUBMIT for every report row whose sub-activity carries
activity_master.requires_pm_approval (0090). Its key is
(report_id, day_part, sub_activity_id) - stable across draft re-saves, which
delete and re-insert every task row. A rejection followed by a correction opens
a NEW row (cycle_no + 1, previous_request_id -> the rejected one), so no
decision is ever overwritten.

Snapshots (names, remarks, day part, report date) are frozen at submit so the
request keeps its original context if the Activity Master or the report later
changes. report_id is SET NULL so history survives even a reopened-then-deleted
draft.

Revision ID: 0091_rework_approval_requests
Revises: 0090_activity_pm_approval
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "0091_rework_approval_requests"
down_revision: Union[str, None] = "0090_activity_pm_approval"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "rework_approval_requests",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "report_id", UUID,
            sa.ForeignKey("daily_work_reports.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "employee_id", UUID,
            sa.ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "project_id", UUID,
            sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column(
            "activity_id", UUID,
            sa.ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=True,
        ),
        sa.Column(
            "sub_activity_id", UUID,
            sa.ForeignKey("activity_master.id", ondelete="RESTRICT"), nullable=False,
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("day_part", sa.String(20), nullable=False),
        sa.Column("project_code", sa.Text(), nullable=True),
        sa.Column("project_name", sa.Text(), nullable=True),
        sa.Column("activity_name", sa.Text(), nullable=True),
        sa.Column("sub_activity_name", sa.Text(), nullable=False),
        sa.Column("employee_remarks", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("cycle_no", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "previous_request_id", UUID,
            sa.ForeignKey("rework_approval_requests.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "requested_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.text("now()"),
        ),
        sa.Column(
            "requested_by", UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column(
            "reviewer_id", UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("review_remarks", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'cancelled')",
            name="rework_approval_requests_status_valid",
        ),
        sa.CheckConstraint(
            "day_part IN ('full_day', 'first_half', 'second_half')",
            name="rework_approval_requests_day_part_valid",
        ),
        sa.CheckConstraint("cycle_no >= 1", name="rework_approval_requests_cycle_positive"),
    )
    op.create_index("rework_requests_employee_idx", "rework_approval_requests", ["employee_id"])
    op.create_index("rework_requests_project_idx", "rework_approval_requests", ["project_id"])
    op.create_index("rework_requests_status_idx", "rework_approval_requests", ["status"])
    op.create_index("rework_requests_report_idx", "rework_approval_requests", ["report_id"])
    op.create_index("rework_requests_date_idx", "rework_approval_requests", ["report_date"])
    # The duplicate guard: at most one PENDING cycle per report row key. A
    # double-clicked or retried Submit can never raise a second request.
    op.create_index(
        "rework_requests_one_pending_uq",
        "rework_approval_requests",
        ["report_id", "day_part", "sub_activity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND report_id IS NOT NULL"),
    )

    op.add_column(
        "work_report_tasks",
        sa.Column(
            "rework_request_id", UUID,
            sa.ForeignKey("rework_approval_requests.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "work_report_tasks_rework_request_idx", "work_report_tasks", ["rework_request_id"]
    )


def downgrade() -> None:
    op.drop_index("work_report_tasks_rework_request_idx", table_name="work_report_tasks")
    op.drop_column("work_report_tasks", "rework_request_id")
    op.drop_index("rework_requests_one_pending_uq", table_name="rework_approval_requests")
    op.drop_index("rework_requests_date_idx", table_name="rework_approval_requests")
    op.drop_index("rework_requests_report_idx", table_name="rework_approval_requests")
    op.drop_index("rework_requests_status_idx", table_name="rework_approval_requests")
    op.drop_index("rework_requests_project_idx", table_name="rework_approval_requests")
    op.drop_index("rework_requests_employee_idx", table_name="rework_approval_requests")
    op.drop_table("rework_approval_requests")
