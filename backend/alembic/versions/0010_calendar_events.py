"""0010 company calendar events

Adds the company_calendar_events table for manager-managed holidays/events
visible across all user roles.

Revision ID: 0010_calendar_events
Revises: 0009_leave_requests
Create Date: 2026-06-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_calendar_events"
down_revision: Union[str, None] = "0009_leave_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE calendar_event_type AS ENUM ('holiday', 'event')"
    )
    event_type_enum = postgresql.ENUM(
        "holiday", "event",
        name="calendar_event_type", create_type=False,
    )
    op.create_table(
        "company_calendar_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("event_type", event_type_enum, nullable=False, server_default=sa.text("'holiday'")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("cal_event_date_idx", "company_calendar_events", ["event_date"])
    op.create_index("cal_event_type_idx", "company_calendar_events", ["event_type", "event_date"])


def downgrade() -> None:
    op.drop_index("cal_event_type_idx", table_name="company_calendar_events")
    op.drop_index("cal_event_date_idx", table_name="company_calendar_events")
    op.drop_table("company_calendar_events")
    op.execute("DROP TYPE IF EXISTS calendar_event_type")
