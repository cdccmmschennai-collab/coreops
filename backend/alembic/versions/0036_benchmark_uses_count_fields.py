"""0036 benchmark uses existing count fields

Redesign: NUMERIC benchmarks no longer use a separate `actual_count` entry.
Instead, the engine reads whichever of the work report task's existing
tags_count/docs_count/bom_count/spares_count the sub-activity's
relevant_count_field names, so production numbers are never entered twice.

  - work_report_tasks.actual_count -> dropped
  - work_report_tasks.relevant_count_field_snapshot -> added (frozen at submit,
    same pattern as benchmark_type_snapshot)

The "relevant_count_field required for NUMERIC" check constraint is added
separately in migration 0037, *after* re-running
`scripts/seed_activity_master.py` to backfill it onto existing NUMERIC rows —
splitting it out lets that backfill happen between two plain
`alembic upgrade` steps instead of needing any manual data surgery.

Revision ID: 0036_benchmark_uses_count_fields
Revises: 0035_activity_master
Create Date: 2026-06-16
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_benchmark_uses_count_fields"
down_revision: Union[str, None] = "0035_activity_master"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("work_report_tasks", "actual_count")
    op.add_column("work_report_tasks", sa.Column(
        "relevant_count_field_snapshot", sa.String(20), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("work_report_tasks", "relevant_count_field_snapshot")
    op.add_column("work_report_tasks", sa.Column("actual_count", sa.Integer(), nullable=True))
