"""0005 work reports

Adds the work_report_status enum and the Daily Work Reports tables:
daily_work_reports (header, one row per employee/date) and work_report_tasks
(lines, one per project worked on). total_minutes is derived server-side.

Revision ID: 0005_work_reports
Revises: 0004_attendance
Create Date: 2026-06-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_work_reports"
down_revision: Union[str, None] = "0004_attendance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE work_report_status AS ENUM "
        "('draft', 'submitted', 'approved', 'rejected')"
    )
    status_enum = postgresql.ENUM(
        "draft", "submitted", "approved", "rejected",
        name="work_report_status", create_type=False,
    )

    op.create_table(
        "daily_work_reports",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("status", status_enum, server_default=sa.text("'draft'"), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("total_minutes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("employee_id", "report_date", name="work_reports_emp_date_uq"),
        sa.CheckConstraint(
            "total_minutes >= 0 AND total_minutes <= 1440",
            name="work_reports_total_minutes_range",
        ),
    )
    op.create_index(
        "work_reports_employee_idx", "daily_work_reports", ["employee_id", "report_date"]
    )
    op.create_index("work_reports_status_idx", "daily_work_reports", ["status"])
    op.create_index("work_reports_date_idx", "daily_work_reports", ["report_date"])

    op.create_table(
        "work_report_tasks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("daily_work_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("minutes_spent", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "minutes_spent >= 1 AND minutes_spent <= 1440",
            name="work_report_tasks_minutes_range",
        ),
    )
    op.create_index("work_report_tasks_report_idx", "work_report_tasks", ["report_id"])
    op.create_index("work_report_tasks_project_idx", "work_report_tasks", ["project_id"])


def downgrade() -> None:
    op.drop_index("work_report_tasks_project_idx", table_name="work_report_tasks")
    op.drop_index("work_report_tasks_report_idx", table_name="work_report_tasks")
    op.drop_table("work_report_tasks")
    op.drop_index("work_reports_date_idx", table_name="daily_work_reports")
    op.drop_index("work_reports_status_idx", table_name="daily_work_reports")
    op.drop_index("work_reports_employee_idx", table_name="daily_work_reports")
    op.drop_table("daily_work_reports")
    op.execute("DROP TYPE IF EXISTS work_report_status")
