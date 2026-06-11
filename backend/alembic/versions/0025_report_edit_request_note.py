"""0025 report edit-request note

Adds daily_work_reports.edit_request_note — the author's reason for an edit
request, shown to the reviewer. Cleared when the report is reopened
(reject / grant edit) or resubmitted.

Revision ID: 0025_report_edit_request_note
Revises: 0024_report_status_granted
Create Date: 2026-06-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0025_report_edit_request_note"
down_revision: Union[str, None] = "0024_report_status_granted"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_work_reports",
        sa.Column("edit_request_note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_work_reports", "edit_request_note")
