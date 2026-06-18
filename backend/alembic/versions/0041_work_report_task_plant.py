"""0041 work report task plant

Adds an independent Maintenance Plant selection to each work report task
row (separate from the project's own assigned plant, set in 0040) — an
employee logging a day's work picks which plant they worked at that day,
mirroring the Activity/Sub-Activity picker: select the Maintenance Plant
directly, Planning Plant + descriptions auto-derive and are frozen as
snapshots at save time (same convention as project_name/project_code).

Revision ID: 0041_work_report_task_plant
Revises: 0040_plants
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0041_work_report_task_plant"
down_revision: Union[str, None] = "0040_plants"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("work_report_tasks", sa.Column(
        "maintenance_plant_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("maintenance_plants.id", ondelete="SET NULL"), nullable=True,
    ))
    op.add_column("work_report_tasks", sa.Column("maintenance_plant_code", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("maintenance_plant_description", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("planning_plant_code", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("planning_plant_description", sa.Text(), nullable=True))
    op.create_index(
        "work_report_tasks_maintenance_plant_idx", "work_report_tasks", ["maintenance_plant_id"],
    )


def downgrade() -> None:
    op.drop_index("work_report_tasks_maintenance_plant_idx", table_name="work_report_tasks")
    for col in (
        "planning_plant_description", "planning_plant_code",
        "maintenance_plant_description", "maintenance_plant_code", "maintenance_plant_id",
    ):
        op.drop_column("work_report_tasks", col)
