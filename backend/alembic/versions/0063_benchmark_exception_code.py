"""0063 benchmark exception code on work report activity rows

Adds work_report_tasks.benchmark_exception_code — the STRUCTURED reason a
numeric benchmark row is evaluated as achieved despite an actual below its
target. Phase 1 carries exactly one value, 'NO_FURTHER_AVAILABLE_WORK': every
available TAG was completed, but fewer were available than the target.

Purely additive and backward-compatible:

- NULLABLE with no server default, so every existing work_report_tasks row
  reads NULL = "no exception" and keeps its current benchmark evaluation
  bit-for-bit. Nothing is backfilled, rewritten or recomputed; old reports open,
  edit, resubmit and export exactly as before.
- VARCHAR(40) + CHECK rather than a native Postgres enum, following the
  benchmark_type / access_type / report_mode precedent — widening the allowed
  set later is an ALTER of one constraint, not an enum type migration.
- The constraint permits NULL explicitly, so it can never reject a legacy row.

The real actual count is NOT touched by this migration or by the feature: the
count columns keep storing what the employee entered (40 stays 40). The
exception only changes how that row is EVALUATED, in calculation code.

Revision ID: 0063_benchmark_exception_code
Revises: 0062_leave_cancellation_status
Create Date: 2026-08-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0063_benchmark_exception_code"
down_revision: Union[str, None] = "0062_leave_cancellation_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "work_report_tasks",
        sa.Column("benchmark_exception_code", sa.String(40), nullable=True),
    )
    op.create_check_constraint(
        "work_report_tasks_benchmark_exception_code_valid",
        "work_report_tasks",
        "benchmark_exception_code IS NULL "
        "OR benchmark_exception_code IN ('NO_FURTHER_AVAILABLE_WORK')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "work_report_tasks_benchmark_exception_code_valid",
        "work_report_tasks",
        type_="check",
    )
    op.drop_column("work_report_tasks", "benchmark_exception_code")
