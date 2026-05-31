"""0004 attendance

Adds the attendance_status enum and the attendance_records table
(one row per employee/date, derived total/overtime minutes).

Revision ID: 0004_attendance
Revises: 0003_projects
Create Date: 2026-05-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_attendance"
down_revision: Union[str, None] = "0003_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE attendance_status AS ENUM "
        "('present', 'absent', 'half_day', 'leave', 'holiday', 'weekend')"
    )
    status_enum = postgresql.ENUM(
        "present", "absent", "half_day", "leave", "holiday", "weekend",
        name="attendance_status", create_type=False,
    )

    op.create_table(
        "attendance_records",
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
        sa.Column("attendance_date", sa.Date(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_minutes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("overtime_minutes", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("status", status_enum, nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("employee_id", "attendance_date", name="attendance_emp_date_uq"),
        sa.CheckConstraint(
            "total_minutes >= 0 AND overtime_minutes >= 0", name="attendance_minutes_nonneg"
        ),
        sa.CheckConstraint(
            "check_out_at IS NULL OR check_in_at IS NULL OR check_out_at >= check_in_at",
            name="attendance_out_after_in",
        ),
    )
    op.create_index(
        "attendance_employee_idx", "attendance_records", ["employee_id", "attendance_date"]
    )
    op.create_index("attendance_date_idx", "attendance_records", ["attendance_date"])


def downgrade() -> None:
    op.drop_index("attendance_date_idx", table_name="attendance_records")
    op.drop_index("attendance_employee_idx", table_name="attendance_records")
    op.drop_table("attendance_records")
    op.execute("DROP TYPE IF EXISTS attendance_status")
