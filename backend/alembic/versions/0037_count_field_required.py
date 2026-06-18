"""0037 activity master numeric requires count field

Adds the check constraint requiring relevant_count_field whenever
benchmark_type='NUMERIC' on activity_master. Split out from migration 0036
so `scripts/seed_activity_master.py` can be re-run (backfilling
relevant_count_field onto any existing NUMERIC rows) between the two
migrations, without manual data surgery.

Revision ID: 0037_count_field_required
Revises: 0036_benchmark_uses_count_fields
Create Date: 2026-06-16

Note: revision ids must stay <=32 chars — alembic_version.version_num is
VARCHAR(32) by default in this project's migration history.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0037_count_field_required"
down_revision: Union[str, None] = "0036_benchmark_uses_count_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "activity_master_numeric_requires_count_field",
        "activity_master",
        "benchmark_type <> 'NUMERIC' OR relevant_count_field IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "activity_master_numeric_requires_count_field", "activity_master", type_="check",
    )
