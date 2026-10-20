"""0087 comp off requests

Comp Off Phase 2 - the data foundation for the employee-request / PM-approval
workflow. An employee names the day they worked and the day they want off, in
one request; a PM approves or rejects it whole.

WHY ONE TABLE AND NO LEDGER
===========================
An approved row IS the credit, already scheduled on its own `off_date`.
Pending, rejected and cancelled rows grant nothing, by status alone. A balance
or "used" column would be a second copy of facts the rows already state, and
would have to be kept in step by hand - the same reasoning as 0068
(permission_requests). Usage is derived later from `off_date` and the
attendance row the approval marks.

ADDITIVE ONLY
=============
- Creates the enum type `comp_off_status` and the table `comp_off_requests`.
- Modifies NO existing table, column, constraint, index or enum. The manual
  `comp_off` attendance status (0049), the `comp_off` report day status (0048)
  and the retired `leave_type` value are untouched.
- Touches no existing data. Legacy PM-entered comp-off attendance rows name no
  worked date, so no credit is backfilled from them.

CONSTRAINTS
===========
- `comp_off_dates_differ`: worked_date <> off_date.
- `comp_off_decision_consistent`: pending carries no reviewer/decision time;
  approved and rejected always carry a decision time.
- `comp_off_live_worked_date_uq` / `comp_off_live_off_date_uq`: partial unique
  indexes over (employee_id, date) WHERE status IN ('pending', 'approved'). A
  worked day backs at most one live request and an off day is claimed by at
  most one; rejected and cancelled history is kept and may repeat.

NOT ENFORCEABLE HERE (service phase): one request's off_date equalling another
live request's worked_date for the same employee (a cross-column conflict no
unique index can express), overlap with leave / attendance / holidays, calendar
eligibility of worked_date, and work-report evidence.

Downgrade drops the table and then the enum. Only comp-off requests are lost;
nothing else references this table.

Revision ID: 0087_comp_off_requests
Revises: 0086_permission_recorded
Create Date: 2026-10-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0087_comp_off_requests"
down_revision: Union[str, None] = "0086_permission_recorded"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COMP_OFF_STATUSES = ("pending", "approved", "rejected", "cancelled")
LIVE_PREDICATE = "status IN ('pending', 'approved')"


def upgrade() -> None:
    comp_off_status = postgresql.ENUM(
        *COMP_OFF_STATUSES, name="comp_off_status", create_type=False
    )
    comp_off_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "comp_off_requests",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("worked_date", sa.Date(), nullable=False),
        sa.Column("off_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            comp_off_status,
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("manager_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("worked_date <> off_date", name="comp_off_dates_differ"),
        sa.CheckConstraint(
            "(status = 'pending' AND reviewed_at IS NULL AND manager_id IS NULL)"
            " OR (status IN ('approved', 'rejected') AND reviewed_at IS NOT NULL)"
            " OR status = 'cancelled'",
            name="comp_off_decision_consistent",
        ),
    )
    op.create_index(
        "comp_off_live_worked_date_uq",
        "comp_off_requests",
        ["employee_id", "worked_date"],
        unique=True,
        postgresql_where=sa.text(LIVE_PREDICATE),
    )
    op.create_index(
        "comp_off_live_off_date_uq",
        "comp_off_requests",
        ["employee_id", "off_date"],
        unique=True,
        postgresql_where=sa.text(LIVE_PREDICATE),
    )
    op.create_index("comp_off_status_idx", "comp_off_requests", ["status"])
    op.create_index(
        "comp_off_manager_idx", "comp_off_requests", ["manager_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("comp_off_manager_idx", table_name="comp_off_requests")
    op.drop_index("comp_off_status_idx", table_name="comp_off_requests")
    op.drop_index("comp_off_live_off_date_uq", table_name="comp_off_requests")
    op.drop_index("comp_off_live_worked_date_uq", table_name="comp_off_requests")
    op.drop_table("comp_off_requests")
    postgresql.ENUM(name="comp_off_status").drop(op.get_bind(), checkfirst=True)
