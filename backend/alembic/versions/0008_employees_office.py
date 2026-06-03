"""0008 employees office

Adds nullable office_id FK to employees. Existing employees are unaffected
(office_id remains NULL until assigned by an admin).

Revision ID: 0008_employees_office
Revises: 0007_offices
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_employees_office"
down_revision: Union[str, None] = "0007_offices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column(
            "office_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("offices.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "employees_office_idx",
        "employees",
        ["office_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("employees_office_idx", table_name="employees")
    op.drop_column("employees", "office_id")
