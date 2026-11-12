"""0089 notification seen

Splits "seen" from "read" on notifications.

    notifications.is_seen   BOOLEAN NOT NULL DEFAULT false

- is_seen  - the user has OPENED the notification panel/page since the row
             arrived. Drives the bell / sidebar badge count only. Opening the
             panel flips every unseen row at once.
- is_read  - unchanged: the user clicked that one notification. Drives the bold
             "unread" styling inside the list.

BACKFILL: is_seen = is_read, so anything already read stays out of the badge
and anything still unread keeps counting until the user next opens the panel.

Revision ID: 0089_notification_seen
Revises: 0088_attendance_comp_off_link
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0089_notification_seen"
down_revision: Union[str, None] = "0088_attendance_comp_off_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column("is_seen", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.execute("UPDATE notifications SET is_seen = is_read")


def downgrade() -> None:
    op.drop_column("notifications", "is_seen")
