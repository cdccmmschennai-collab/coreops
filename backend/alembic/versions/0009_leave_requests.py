"""0009 leave requests

Adds leave_type and leave_status enums and the leave_requests table.

Status lifecycle: pending → approved | rejected | cancelled
manager_id is captured at approval time (denormalised for audit — the
employee's manager may change after the fact).

Revision ID: 0009_leave_requests
Revises: 0008_employees_office
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_leave_requests"
down_revision: Union[str, None] = "0008_employees_office"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE leave_type AS ENUM "
        "('casual', 'sick', 'annual', 'comp_off', 'unpaid', 'other')"
    )
    op.execute(
        "CREATE TYPE leave_status AS ENUM "
        "('pending', 'approved', 'rejected', 'cancelled')"
    )

    leave_type_enum = postgresql.ENUM(
        "casual", "sick", "annual", "comp_off", "unpaid", "other",
        name="leave_type", create_type=False,
    )
    leave_status_enum = postgresql.ENUM(
        "pending", "approved", "rejected", "cancelled",
        name="leave_status", create_type=False,
    )

    op.create_table(
        "leave_requests",
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
        sa.Column("leave_type", leave_type_enum, nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            leave_status_enum,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        # manager_id = reviewer's employee record at decision time (audit)
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("manager_comment", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
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
        sa.CheckConstraint("end_date >= start_date", name="leave_dates_order"),
    )
    op.create_index("leave_employee_idx", "leave_requests", ["employee_id", "start_date"])
    op.create_index("leave_manager_idx", "leave_requests", ["manager_id", "status"])
    op.create_index("leave_status_idx", "leave_requests", ["status"])


def downgrade() -> None:
    op.drop_index("leave_status_idx", table_name="leave_requests")
    op.drop_index("leave_manager_idx", table_name="leave_requests")
    op.drop_index("leave_employee_idx", table_name="leave_requests")
    op.drop_table("leave_requests")
    op.execute("DROP TYPE IF EXISTS leave_status")
    op.execute("DROP TYPE IF EXISTS leave_type")
