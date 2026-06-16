"""0039 notifications severity

Adds severity + resolved_at to the existing notifications table, rather than
a separate "notification center" table — the spec's requested fields
(id/user_id/type/title/message/severity/is_read/created_at) are this table
plus exactly these two columns.

  - severity     -> INFO | WARNING | CRITICAL (new column, default INFO)
  - resolved_at  -> NULL = still an active/unresolved condition; stamped when
                    the underlying benchmark shortfall / overdue task clears.
                    De-duplication (one persistent notification per
                    (user_id, entity_type, entity_id, type)) is enforced in
                    the service layer, not a DB constraint, to keep this
                    additive and simple.

Revision ID: 0039_notifications_severity
Revises: 0038_work_report_tasks_due_dates
Create Date: 2026-06-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0039_notifications_severity"
down_revision: Union[str, None] = "0038_work_report_tasks_due_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column(
        "severity", sa.String(20), nullable=False, server_default="INFO",
    ))
    op.add_column("notifications", sa.Column(
        "resolved_at", sa.DateTime(timezone=True), nullable=True,
    ))
    op.create_check_constraint(
        "notifications_severity_valid",
        "notifications",
        "severity IN ('INFO', 'WARNING', 'CRITICAL')",
    )


def downgrade() -> None:
    op.drop_constraint("notifications_severity_valid", "notifications", type_="check")
    op.drop_column("notifications", "resolved_at")
    op.drop_column("notifications", "severity")
