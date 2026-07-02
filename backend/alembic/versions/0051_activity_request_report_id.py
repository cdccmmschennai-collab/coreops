"""0051 activity_requests.report_id

Links an activity request to the work report it belongs to, so an approved
request can be converted into a normal activity row in that report, and the
employee's form can show its own pending/rejected requests for the report.

Nullable so any pre-existing rows stay valid; new requests always set it.

Revision ID: 0051_activity_request_report_id
Revises: 0050_activity_requests
Create Date: 2026-07-01
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0051_activity_request_report_id"
down_revision: Union[str, None] = "0050_activity_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activity_requests",
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "activity_requests_report_fk",
        "activity_requests",
        "daily_work_reports",
        ["report_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "activity_requests_report_idx", "activity_requests", ["report_id"]
    )


def downgrade() -> None:
    op.drop_index("activity_requests_report_idx", table_name="activity_requests")
    op.drop_constraint(
        "activity_requests_report_fk", "activity_requests", type_="foreignkey"
    )
    op.drop_column("activity_requests", "report_id")
