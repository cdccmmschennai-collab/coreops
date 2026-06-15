"""0028 project_delivery (stub)

This revision was applied to the shared dev DB from another branch
(project-delivery-tracking feature). This stub lets Alembic locate the
revision so the app can start on branches that don't carry the full
migration body. The DB schema is already at this state.

Revision ID: 0028_project_delivery
Revises: 0027_work_report_task_minutes
Create Date: 2026-06-15
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0028_project_delivery"
down_revision: Union[str, None] = "0027_work_report_task_minutes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
