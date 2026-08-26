"""0077 remember which report a continuation decision landed on

Rejecting a continuation WITHDRAWS the rows entered under it (migration 0076 is
what makes finding exactly those rows possible). That is deliberate - unaccepted
work must not survive on the report looking accepted - but it also erased the
only link between the request and the report, so the employee lost every trace
of what they had asked for and why it was refused.

`continuation_requests.affected_report_id` is that link, stamped at DECISION
time (approve and reject alike) from the rows while they still exist. It carries
no approval state of its own - continuation_requests.status remains the single
source of truth for that - it only records WHERE the decision applied, so:

  * the report detail page can still show a "Continuation rejected" record, with
    the reviewer and their note, after the rows are gone;
  * the employee's decision notification resolves its destination from a stored
    value instead of a query that a rejection has already emptied.

ON DELETE SET NULL: deleting a draft report must never delete the request record
that decided it.

Revision ID: 0077_continuation_report_link
Revises: 0076_task_continuation_link
Create Date: 2026-08-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0077_continuation_report_link"
down_revision: Union[str, None] = "0076_task_continuation_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "continuation_requests",
        sa.Column("affected_report_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "continuation_requests_affected_report_fk",
        "continuation_requests",
        "daily_work_reports",
        ["affected_report_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "continuation_requests_affected_report_idx",
        "continuation_requests",
        ["affected_report_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "continuation_requests_affected_report_idx",
        table_name="continuation_requests",
    )
    op.drop_constraint(
        "continuation_requests_affected_report_fk",
        "continuation_requests",
        type_="foreignkey",
    )
    op.drop_column("continuation_requests", "affected_report_id")
