"""0040 plants

Creates the planning_plants / maintenance_plants master-data tables (SAP plant
reference codes — Qatar Petroleum Planning Plants, each with several
Maintenance Plants underneath) and links projects to a Maintenance Plant.
Also lifts the projects.code immutability: it's purely a schema/service-layer
rule (no DB constraint enforced it), so no DDL is needed for that part — see
the projects module diff.

Revision ID: 0040_plants
Revises: 0039_notifications_severity
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0040_plants"
down_revision: Union[str, None] = "0039_notifications_severity"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_plants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "planning_plants_code_uq", "planning_plants", ["code"],
        unique=True, postgresql_where=sa.text("is_active = true"),
    )

    op.create_table(
        "maintenance_plants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("planning_plant_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("planning_plants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "maintenance_plants_code_uq", "maintenance_plants", ["code"],
        unique=True, postgresql_where=sa.text("is_active = true"),
    )
    op.create_index(
        "maintenance_plants_planning_plant_idx", "maintenance_plants", ["planning_plant_id"],
    )

    op.add_column("projects", sa.Column(
        "maintenance_plant_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("maintenance_plants.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index("projects_maintenance_plant_idx", "projects", ["maintenance_plant_id"])


def downgrade() -> None:
    op.drop_index("projects_maintenance_plant_idx", table_name="projects")
    op.drop_column("projects", "maintenance_plant_id")

    op.drop_index("maintenance_plants_planning_plant_idx", table_name="maintenance_plants")
    op.drop_index("maintenance_plants_code_uq", table_name="maintenance_plants")
    op.drop_table("maintenance_plants")

    op.drop_index("planning_plants_code_uq", table_name="planning_plants")
    op.drop_table("planning_plants")
