"""0061 employee activity access (restricted activities)

Adds activity-level employee authorization on top of Activity Master. Two
changes, both additive — nothing existing is rewritten or dropped:

1. activity_master + access_type VARCHAR(20) NOT NULL DEFAULT 'COMMON'
   (VARCHAR + CHECK, following the benchmark_type / report_mode precedent — no
   new Postgres enum type to manage). Every existing activity is backfilled to
   'COMMON', so the pre-0061 behaviour (all employees can select every active
   activity) is preserved bit-for-bit. The column is created NOT NULL with the
   default in one step, so the backfill is implicit and no historical
   Activity / Sub-Activity / Report / Benchmark / Work Item row is touched.

2. NEW TABLE employee_activity_access — one soft-revocable row per
   (activity, employee) grant. is_active=false + revoked_by_id/revoked_at is a
   revoke; re-granting reactivates the same row (unique (activity_id,
   employee_id)). Indexes cover the three hot lookups: active employees for one
   activity, one employee's access to one activity, and all active restricted
   activities for one employee.

Downgrade drops the new table and the new column only. It never reads or
modifies any report / work_report_tasks / work_items row — historical activity
references are foreign keys into activity_master, which is left intact.

Revision ID: 0061_employee_activity_access
Revises: 0060_work_report_periods
Create Date: 2026-07-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0061_employee_activity_access"
down_revision: Union[str, None] = "0060_work_report_periods"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. access_type on activity_master. NOT NULL DEFAULT 'COMMON' backfills every
    #    existing row to COMMON in the same statement (no separate UPDATE needed).
    op.add_column(
        "activity_master",
        sa.Column(
            "access_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'COMMON'"),
        ),
    )
    op.create_check_constraint(
        "activity_master_access_type_valid",
        "activity_master",
        "access_type IN ('COMMON', 'RESTRICTED')",
    )

    # 2. employee_activity_access mapping table.
    op.create_table(
        "employee_activity_access",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activity_master.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "granted_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "revoked_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.UniqueConstraint(
            "activity_id", "employee_id", name="employee_activity_access_pair_uq"
        ),
    )
    op.create_index(
        "employee_activity_access_activity_active_idx",
        "employee_activity_access",
        ["activity_id", "is_active"],
    )
    op.create_index(
        "employee_activity_access_employee_activity_idx",
        "employee_activity_access",
        ["employee_id", "activity_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "employee_activity_access_employee_activity_idx",
        table_name="employee_activity_access",
    )
    op.drop_index(
        "employee_activity_access_activity_active_idx",
        table_name="employee_activity_access",
    )
    op.drop_table("employee_activity_access")
    op.drop_constraint(
        "activity_master_access_type_valid", "activity_master", type_="check"
    )
    op.drop_column("activity_master", "access_type")
