"""0045 employee leave balances

Adds manually-maintained leave balances (Phase 1 — no accrual/automation).

  employee_leave_balances          one active row per employee; available_leave
                                   is the source of truth for the "Available
                                   Leave" figure shown to employees.
  employee_leave_balance_history   append-only trail; every balance change
                                   writes one row (old/new/reason/updated_by).

The history table is intentionally immutable (only created_at is tracked).

Revision ID: 0045_employee_leave_balances
Revises: 0044_project_planning_plant
Create Date: 2026-06-24
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_employee_leave_balances"
down_revision: Union[str, None] = "0044_project_planning_plant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "employee_leave_balances",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # available_leave may be negative (loss-of-pay): e.g. -0.5 half-day LOP.
        sa.Column(
            "available_leave",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
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
    # One active record per employee.
    op.create_index(
        "leave_balance_employee_uq",
        "employee_leave_balances",
        ["employee_id"],
        unique=True,
    )

    op.create_table(
        "employee_leave_balance_history",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_balance", sa.Numeric(5, 2), nullable=True),
        sa.Column("new_balance", sa.Numeric(5, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "updated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "leave_balance_history_employee_idx",
        "employee_leave_balance_history",
        ["employee_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "leave_balance_history_employee_idx",
        table_name="employee_leave_balance_history",
    )
    op.drop_table("employee_leave_balance_history")
    op.drop_index("leave_balance_employee_uq", table_name="employee_leave_balances")
    op.drop_table("employee_leave_balances")
