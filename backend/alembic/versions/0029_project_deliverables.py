"""0029 project_deliverables

Adds the project_deliverables table: a simple CRUD entity scoped to a project
that tracks named deliverables (name, description, target_date, owner, status,
completion_date).  Status is a 3-value enum (pending / in_progress / completed);
overdue detection is computed at query time and NOT stored here.

Revision ID: 0029_project_deliverables
Revises: 0028_project_delivery
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_project_deliverables"
down_revision: Union[str, None] = "0028_project_delivery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE deliverable_status AS ENUM ('pending', 'in_progress', 'completed')"
    )
    op.execute(
        """
        CREATE TABLE project_deliverables (
            id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            project_id          uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            name                text NOT NULL,
            description         text,
            target_date         date,
            owner_employee_id   uuid REFERENCES employees(id) ON DELETE SET NULL,
            status              deliverable_status NOT NULL DEFAULT 'pending',
            completion_date     date,
            created_at          timestamptz NOT NULL DEFAULT now(),
            updated_at          timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX project_deliverables_project_idx ON project_deliverables(project_id)"
    )
    op.execute(
        "CREATE INDEX project_deliverables_owner_idx  ON project_deliverables(owner_employee_id)"
    )
    op.execute(
        "CREATE INDEX project_deliverables_status_idx ON project_deliverables(status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS project_deliverables")
    op.execute("DROP TYPE IF EXISTS deliverable_status")
