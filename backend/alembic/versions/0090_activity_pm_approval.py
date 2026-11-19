"""0090 activity pm approval

Rework Activity Approval - Phase 1 (configuration only).

    activity_master.requires_pm_approval   BOOLEAN NOT NULL DEFAULT false

An explicit, per-SUB-ACTIVITY flag: true means a work report row on this
sub-activity needs Project Manager approval once the report is submitted.
Nothing is derived from the name - "Rework" in a name is only a search hint in
the Settings UI. A top-level Activity can never carry the flag (CHECK below), so
flagging a parent can never silently cover its children.

BACKFILL: none. Every existing row starts false, so no report changes behaviour
until an administrator configures a sub-activity.

Revision ID: 0090_activity_pm_approval
Revises: 0089_notification_seen
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0090_activity_pm_approval"
down_revision: Union[str, None] = "0089_notification_seen"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "activity_master",
        sa.Column(
            "requires_pm_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_check_constraint(
        "activity_master_pm_approval_sub_only",
        "activity_master",
        "requires_pm_approval = false OR level = 'sub_activity'",
    )
    # The configured list is tiny next to the whole master; a partial index
    # keeps the Settings listing and the submit-time lookup cheap.
    op.create_index(
        "activity_master_pm_approval_idx",
        "activity_master",
        ["id"],
        postgresql_where=sa.text("requires_pm_approval = true"),
    )


def downgrade() -> None:
    op.drop_index("activity_master_pm_approval_idx", table_name="activity_master")
    op.drop_constraint(
        "activity_master_pm_approval_sub_only", "activity_master", type_="check"
    )
    op.drop_column("activity_master", "requires_pm_approval")
