"""0044 project planning plant

Adds a direct Planning Plant link to each project (project master).

The project master supplied by the PM ties each project to a Planning Plant
(code + description) and a Job Code — there is no Maintenance Plant on the
project itself. Maintenance Plants hang off the Planning Plant
(maintenance_plants.planning_plant_id, added in 0040) and are selected at
usage time once that master data is loaded. This column makes the project ->
Planning Plant relationship explicit so the Maintenance Plant dropdown can be
filtered by the project's planning_plant_code later without a schema change.

The pre-existing projects.maintenance_plant_id column (0040) is retained for
backward compatibility; new project master rows leave it null.

Revision ID: 0044_project_planning_plant
Revises: 0043_task_due_date_assigned_day
Create Date: 2026-06-22
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0044_project_planning_plant"
down_revision: Union[str, None] = "0043_task_due_date_assigned_day"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("projects", sa.Column(
        "planning_plant_id", postgresql.UUID(as_uuid=True),
        sa.ForeignKey("planning_plants.id", ondelete="SET NULL"), nullable=True,
    ))
    op.create_index(
        "projects_planning_plant_idx", "projects", ["planning_plant_id"],
    )


def downgrade() -> None:
    op.drop_index("projects_planning_plant_idx", table_name="projects")
    op.drop_column("projects", "planning_plant_id")
