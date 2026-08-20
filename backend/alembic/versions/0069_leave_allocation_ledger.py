"""0069 leave allocation ledger

Turns the leave balance from ONE MUTABLE NUMBER into a per-month derived ledger,
so that carry-forward, an employee-specific `Leave/month`, and a PM correction
that does not destroy the automatic accrual can all coexist and stay
historically correct.

    closing(M) = carry_in(M) + allocation(M) + adjustment(M) - consumed(M)

WHAT IS ADDED
=============
  employee_leave_allocations   the employee's `Leave/month`, EFFECTIVE-DATED.
                               One row per POLICY CHANGE, never one per month.
                               Raising somebody to 2 d/month effective March adds
                               a second row; January and February keep reading
                               the first one forever. UNIQUE(employee, month).

  employee_leave_adjustments   append-only signed corrections, each stamped with
                               the month it belongs to. The PM's manual
                               correction, and the opening balances this
                               migration carries over.

Neither table stores a balance, and neither has a row per month per employee:
the ledger derives every month from these rows plus the `leave` days already on
`attendance_records`. That is what makes a page refresh unable to accrue twice.

WHY THE OLD TABLE IS NOT DROPPED
================================
`employee_leave_balances` holds the only copy of three real balances
(2.50 / 2.00 / 5.00). This migration copies each of them into an opening
adjustment and then STOPS READING the table - it is left in place, still
populated, as the pre-ledger snapshot and the rollback path. Dropping it is a
separate migration, to be written only once the derived figures have been
verified against it in production. Two readers would be two sources of truth;
one reader and one frozen snapshot is not.

`employee_leave_balance_history` is untouched and keeps its role: the audit trail
of PM corrections. Nothing in it is deleted or rewritten.

THE OPENING BALANCE, AND WHY IT ADDS BACK THE MONTH'S LEAVE
===========================================================
`available_leave` is a figure as of TODAY - the month's already-approved leave has
already been subtracted from it by `leave/effects`. The ledger will subtract that
same leave again when it counts the month's `leave` attendance rows. So the
opening adjustment is

    days = available_leave + (leave days already marked in the opening month)

which makes the derived closing balance for the opening month come out at exactly
`available_leave`. For EMP225: 2.50 + 1 marked day = 3.50, and
3.50 + 0 allocation - 1 consumed = 2.50. Unchanged, which is the point.

`unpaid` leave days are excluded from that add-back for the same reason the
ledger excludes them from consumption - they were never deducted in the first
place, so adding them back would invent a day.

NO ALLOCATION ROWS ARE CREATED
==============================
`Leave/month` starts empty for every employee. Inventing 2 d/month for 29 people
would hand out leave nobody granted; the PM sets each value from the Leave
Balance tab. An employee with no allocation accrues nothing and carries their
balance forward untouched - exactly how they behave today.

NEGATIVE BALANCES STAY REPRESENTABLE
====================================
`adjustments.days` is a signed NUMERIC(6,2) with no lower bound, and the derived
total is not clamped. Loss-of-pay (-0.5, -2) and a PM correction that takes a
month negative both survive. There is deliberately no `>= 0` constraint anywhere
in this migration.

Downgrade drops only the two new tables. Nothing is lost: `employee_leave_balances`
still holds every pre-migration value.

Revision ID: 0069_leave_allocation_ledger
Revises: 0068_permission_requests
Create Date: 2026-08-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0069_leave_allocation_ledger"
down_revision: Union[str, None] = "0068_permission_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The month the migrated balances open in. Everything before it is outside the
# ledger and reads as "no ledger yet" rather than as a zero balance, because
# there is no honest way to reconstruct a monthly history that was never kept.
OPENING_MONTH = "2026-08-01"

# Carries each existing balance into the ledger, adding back the funded leave
# already marked in the opening month so the derived closing balance for that
# month equals the figure the employee sees today. Employees with no balance row
# get nothing - they had no balance to preserve.
_BACKFILL = sa.text(
    """
    INSERT INTO employee_leave_adjustments
        (employee_id, effective_month, days, reason, created_by)
    SELECT
        b.employee_id,
        CAST(:opening_month AS date),
        b.available_leave + COALESCE(marked.days, 0),
        'Opening balance carried over from the manual leave balance '
            '(migration 0069).',
        NULL
    FROM employee_leave_balances b
    LEFT JOIN LATERAL (
        SELECT COUNT(*)::numeric AS days
        FROM attendance_records a
        WHERE a.employee_id = b.employee_id
          AND a.status = 'leave'
          AND a.attendance_date >= CAST(:opening_month AS date)
          AND a.attendance_date
              < (CAST(:opening_month AS date) + INTERVAL '1 month')
          -- Unpaid days were never deducted from the balance, so they must not
          -- be added back; the ledger will not subtract them either.
          AND NOT EXISTS (
              SELECT 1 FROM leave_requests r
              WHERE r.employee_id = b.employee_id
                AND r.leave_type = 'unpaid'
                AND r.status IN ('approved', 'cancellation_requested')
                AND a.attendance_date BETWEEN r.start_date AND r.end_date
          )
    ) AS marked ON TRUE
    """
)


def upgrade() -> None:
    op.create_table(
        "employee_leave_allocations",
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
        # Always the first of a month: allocation is granted per calendar month,
        # and a mid-month effective date would make "what did March accrue"
        # ambiguous.
        sa.Column("effective_from", sa.Date(), nullable=False),
        # Fractional rates are allowed (0.5 d/month) because the leave system
        # already deals in halves. Never negative - a grant is not a deduction.
        sa.Column(
            "monthly_days",
            sa.Numeric(5, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
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
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "date_part('day', effective_from) = 1",
            name="leave_allocation_effective_month_start",
        ),
        sa.CheckConstraint("monthly_days >= 0", name="leave_allocation_nonneg"),
    )
    # One rate per employee per effective month, so re-saving the same effective
    # month is an update rather than a second competing row.
    op.create_index(
        "leave_allocation_employee_month_uq",
        "employee_leave_allocations",
        ["employee_id", "effective_from"],
        unique=True,
    )

    op.create_table(
        "employee_leave_adjustments",
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
        sa.Column("effective_month", sa.Date(), nullable=False),
        # SIGNED, and deliberately unbounded below: the existing system
        # represents loss-of-pay as a negative balance.
        sa.Column("days", sa.Numeric(6, 2), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_by",
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
        sa.CheckConstraint(
            "date_part('day', effective_month) = 1",
            name="leave_adjustment_month_start",
        ),
    )
    # Not unique: several corrections in one month are several events, and the
    # ledger sums them rather than letting the last one win.
    op.create_index(
        "leave_adjustment_employee_month_idx",
        "employee_leave_adjustments",
        ["employee_id", "effective_month"],
    )

    op.execute(_BACKFILL.bindparams(opening_month=OPENING_MONTH))


def downgrade() -> None:
    op.drop_index(
        "leave_adjustment_employee_month_idx",
        table_name="employee_leave_adjustments",
    )
    op.drop_table("employee_leave_adjustments")
    op.drop_index(
        "leave_allocation_employee_month_uq",
        table_name="employee_leave_allocations",
    )
    op.drop_table("employee_leave_allocations")
