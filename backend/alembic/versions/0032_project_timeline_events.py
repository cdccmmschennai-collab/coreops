"""0032 project timeline events

Append-only log of structural changes to a project:
project_created, planned_date_changed, member_added, member_removed,
submission_created, submission_updated.

Revision ID: 0032_project_timeline_events
Revises: 0031_project_planned_dates
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0032_project_timeline_events"
down_revision: Union[str, None] = "0031_project_planned_dates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_timeline_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="project_timeline_events_pkey"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE",
            name="project_timeline_events_project_fk",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], ondelete="SET NULL",
            name="project_timeline_events_actor_fk",
        ),
    )
    op.create_index(
        "project_timeline_events_project_idx",
        "project_timeline_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("project_timeline_events_project_idx")
    op.drop_table("project_timeline_events")
