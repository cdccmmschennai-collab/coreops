"""0011 notifications

Adds the notifications table: persisted in-app notifications for workflow events.
One row per (user, event). Indexed for fast inbox and unread-count queries.

Revision ID: 0011_notifications
Revises: 0010_calendar_events
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_notifications"
down_revision: Union[str, None] = "0010_calendar_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("notif_user_idx", "notifications", ["user_id", "created_at"])
    op.create_index(
        "notif_unread_idx", "notifications", ["user_id"],
        postgresql_where=sa.text("is_read = false"),
    )
    op.create_index("notif_created_idx", "notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("notif_created_idx", table_name="notifications")
    op.drop_index("notif_unread_idx", table_name="notifications")
    op.drop_index("notif_user_idx", table_name="notifications")
    op.drop_table("notifications")
