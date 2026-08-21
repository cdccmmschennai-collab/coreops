"""0071 prod status plant

(Production Status -> Maintenance Plant. The revision id is abbreviated because
`alembic_version.version_num` is VARCHAR(32) and the descriptive form does not
fit.)

Adds ONE nullable column to `project_production_statuses`:

  maintenance_plant_id  UUID NULL -> maintenance_plants.id ON DELETE SET NULL

Why a reference and not copied plant data
    The Maintenance Plant already exists as master data (`maintenance_plants`,
    seeded from SAP by scripts/seed_plants.py) and is already referenced this
    exact way by `work_report_tasks.maintenance_plant_id` - nullable FK,
    ON DELETE SET NULL, plus a plain index. This migration follows that
    precedent rather than inventing a second plant source or duplicating the
    plant's code/description onto the production status row.

    The plant a production status belongs to is therefore a pointer into
    existing master data. Which plants are valid for a given project is decided
    by the project's Planning Plant relationship (the same scoping the Project
    Edit page's dropdown uses), and that rule is enforced in the service - not
    by a constraint here, because the project's Planning Plant can legitimately
    change later and an old record must keep the plant it was recorded against.

Existing rows
    NULL. The column is nullable with no server default and no backfill, so
    every production status recorded before this migration stays valid and
    simply has no plant. No historical plant assignment is invented, and
    nothing about the append-only history model changes.

Not touched: no other column, no constraint, no index, no row. The
project + revision + activity identity of a production status is unchanged -
the plant is carried BY a record, it is not part of what makes one record
distinct from another (see the module docstring in production_status/models.py).

Downgrade drops the index and the column, returning the schema exactly to 0070.
Reversible, and lossy only in the sense that any recorded plant selections are
discarded - which is unavoidable when the column itself goes away.

Revision ID: 0071_prod_status_plant
Revises: 0070_project_production_status
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0071_prod_status_plant"
down_revision: Union[str, None] = "0070_project_production_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_production_statuses",
        sa.Column(
            "maintenance_plant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("maintenance_plants.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Plain single-column index, same as work_report_tasks' - the column is
    # read by id when a report resolves each row's plant label.
    op.create_index(
        "project_production_statuses_maintenance_plant_idx",
        "project_production_statuses",
        ["maintenance_plant_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "project_production_statuses_maintenance_plant_idx",
        table_name="project_production_statuses",
    )
    op.drop_column("project_production_statuses", "maintenance_plant_id")
