"""0015 activity type optional code

Activity types created from work reports may have no SAP-style code.
Partial unique index applies only when code IS NOT NULL.

Revision ID: 0015_activity_type_optional_code
Revises: 0014_project_job_code
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015_activity_type_optional_code"
down_revision: Union[str, None] = "0014_project_job_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("activity_types_code_uq", table_name="activity_types")
    op.alter_column("activity_types", "code", existing_type=sa.String(10), nullable=True)
    op.create_index(
        "activity_types_code_uq",
        "activity_types",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND code IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("activity_types_code_uq", table_name="activity_types")
    op.execute(
        "UPDATE activity_types SET code = LEFT(UPPER(REPLACE(name, ' ', '-')), 10) "
        "WHERE code IS NULL"
    )
    op.alter_column("activity_types", "code", existing_type=sa.String(10), nullable=False)
    op.create_index(
        "activity_types_code_uq",
        "activity_types",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
