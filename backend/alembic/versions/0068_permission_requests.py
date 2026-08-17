"""0068 permission requests

Phase 11 - the Permission foundation. "Permission" here is the HR sense used on
the shop floor: an hour or two of sanctioned absence inside an otherwise normal
working day. It has nothing to do with RBAC capabilities.

WHY A NEW TABLE
===============
Nothing in CoreOps could hold this. `leave_requests` is day-scale and its
approval writes whole `attendance_records` days, which is precisely what a
permission must NOT do - a permission day stays `present`. Overloading leave
with an hours column would put two different units and two different attendance
effects behind one status machine.

WHY NO BALANCE TABLE
====================
The monthly allowance is a CONSTANT (4h), so the remaining balance is
`4 - SUM(duration_hours WHERE status = 'approved')` over the requests of that
calendar month. Deriving it is not a shortcut, it is what makes the stated rules
true by construction:

  - a pending request cannot consume balance, because only `approved` is summed;
  - a rejection cannot consume balance, for the same reason;
  - cancelling an approved request restores EXACTLY what it took, because the row
    stops being summed - there is no stored figure to adjust;
  - cancelling twice cannot restore twice, because there is nothing to add to;
  - unused hours cannot carry forward, because each month sums only its own rows.

A stored monthly counter would have to be kept in step with all five of those by
hand. `employee_leave_balances` is also the wrong home regardless: it is one row
per employee holding DAYS of annual leave with no period column, and Phase 10's
leave deduction already owns it.

ADDITIVE ONLY
=============
- Creates the enum type `permission_status` and the table `permission_requests`.
- Modifies NO existing table, column, constraint, index or enum. In particular
  `attendance_records` is untouched: a permission day keeps `status = 'present'`
  and its hours live only here, joinable by (employee_id, date). That join is the
  hook Phase 12 will use; this migration does not create it.
- Touches no existing data. Nothing is read, backfilled, guessed or deleted. The
  table starts empty, so every employee correctly reads 4h remaining.
- `duration_hours` is CHECK-constrained to (1, 2) in the DATABASE as well as in
  the API schema. The "no 30-minute permission" rule is a hard invariant, so it
  is enforced where a stray script cannot get around it.
- `created_at` IS the requested-at timestamp; there is no second column for it.
  `manager_id` is the reviewer, denormalised at decision time exactly as
  `leave_requests.manager_id` is, so a later change of manager cannot rewrite who
  actually decided.

Downgrade drops the table and then the enum. The only thing lost is permission
requests themselves - no leave, attendance or balance data is reachable from
here, so nothing else can be damaged by rolling back.

Revision ID: 0068_permission_requests
Revises: 0067_attendance_record_note
Create Date: 2026-08-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0068_permission_requests"
down_revision: Union[str, None] = "0067_attendance_record_note"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Four statuses, deliberately. Leave has a fifth (`cancellation_requested`)
# because an approved absence stands until a manager rules on its withdrawal; a
# permission is one or two hours, so a withdrawal has nothing to hold open.
PERMISSION_STATUSES = ("pending", "approved", "rejected", "cancelled")


def upgrade() -> None:
    permission_status = postgresql.ENUM(
        *PERMISSION_STATUSES, name="permission_status", create_type=False
    )
    permission_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "permission_requests",
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
        sa.Column("permission_date", sa.Date(), nullable=False),
        sa.Column("duration_hours", sa.SmallInteger(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "status",
            permission_status,
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
        sa.CheckConstraint(
            "duration_hours IN (1, 2)", name="permission_duration_1h_or_2h"
        ),
    )
    op.create_index(
        "permission_employee_date_idx",
        "permission_requests",
        ["employee_id", "permission_date"],
    )
    op.create_index("permission_status_idx", "permission_requests", ["status"])
    op.create_index(
        "permission_manager_idx", "permission_requests", ["manager_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("permission_manager_idx", table_name="permission_requests")
    op.drop_index("permission_status_idx", table_name="permission_requests")
    op.drop_index("permission_employee_date_idx", table_name="permission_requests")
    op.drop_table("permission_requests")
    postgresql.ENUM(name="permission_status").drop(op.get_bind(), checkfirst=True)
