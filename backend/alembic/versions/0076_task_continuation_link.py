"""0076 link a saved task row to the continuation request that governs it

Phase 3 correction. Before this, a lump-sum continuation saved past its allowed
duration was indistinguishable on the report from ordinary accepted work: the
row existed, the ContinuationRequest existed, and nothing tied one to the other.
Two consequences, both wrong:

  * a PENDING continuation read as final recorded work the moment the employee
    submitted the report;
  * a REJECTED continuation stayed on the report as if it had been accepted -
    there was no way to find the rows the rejection was about.

`work_report_tasks.continuation_request_id` is that tie. Every row entered while
a continuation request governs the work item carries the request's id, so the
row's approval state is DERIVED from the request (one source of truth, no second
status column that could drift) and a rejection can find and withdraw exactly
the rows it decided against - and nothing else on the report.

A request governs every row dated on or after its continuation_date, not just
the first blocked day: while a request is pending the employee may keep
reporting, and each of those days belongs to the same decision.

ON DELETE SET NULL, not CASCADE: losing a request record must never silently
delete work-report history. NULL is the normal state - it means "this row needed
no approval", which is every row on every non-lump-sum activity and every
lump-sum row still inside its allowance.

Revision ID: 0076_task_continuation_link
Revises: 0075_ls_workday_duration
Create Date: 2026-08-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0076_task_continuation_link"
down_revision: Union[str, None] = "0075_ls_workday_duration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "work_report_tasks",
        sa.Column("continuation_request_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "work_report_tasks_continuation_request_fk",
        "work_report_tasks",
        "continuation_requests",
        ["continuation_request_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "work_report_tasks_continuation_request_idx",
        "work_report_tasks",
        ["continuation_request_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "work_report_tasks_continuation_request_idx", table_name="work_report_tasks"
    )
    op.drop_constraint(
        "work_report_tasks_continuation_request_fk",
        "work_report_tasks",
        type_="foreignkey",
    )
    op.drop_column("work_report_tasks", "continuation_request_id")
