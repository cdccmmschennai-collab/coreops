"""0012 master data tables

Adds activity_types and job_codes as standalone master reference tables.
Zero impact on existing tables. These tables are seeded from Excel via
backend/scripts/seed_master_data.py after upgrade.

Revision ID: 0012_master_data
Revises: 0011_notifications
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_master_data"
down_revision: Union[str, None] = "0011_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "activity_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        # GENERAL | PROJECT | TAG_ESTIMATION
        sa.Column("category", sa.String(30), nullable=False, server_default="GENERAL"),
        sa.Column("requires_project", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_index(
        "activity_types_code_uq",
        "activity_types",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index("activity_types_category_idx", "activity_types", ["category"])
    op.create_index("activity_types_active_idx", "activity_types", ["is_active"])

    op.create_table(
        "job_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
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
    op.create_index(
        "job_codes_code_uq",
        "job_codes",
        ["code"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )
    op.create_index("job_codes_active_idx", "job_codes", ["is_active"])


def downgrade() -> None:
    op.drop_index("job_codes_active_idx", table_name="job_codes")
    op.drop_index("job_codes_code_uq", table_name="job_codes")
    op.drop_table("job_codes")

    op.drop_index("activity_types_active_idx", table_name="activity_types")
    op.drop_index("activity_types_category_idx", table_name="activity_types")
    op.drop_index("activity_types_code_uq", table_name="activity_types")
    op.drop_table("activity_types")
