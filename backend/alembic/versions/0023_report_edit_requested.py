"""0023 report edit-requested timestamp

Adds daily_work_reports.edit_requested_at — set when an author asks a reviewer
(PM, or a team lead on one of the report's projects) to reopen a submitted
report for editing. Cleared when the report is reopened (reject / grant edit)
or resubmitted.

Revision ID: 0023_report_edit_requested
Revises: 0022_day_status_office
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0023_report_edit_requested"
down_revision: Union[str, None] = "0022_day_status_office"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_work_reports",
        sa.Column("edit_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_work_reports", "edit_requested_at")
