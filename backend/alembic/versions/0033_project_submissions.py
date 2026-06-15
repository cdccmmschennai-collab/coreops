"""0033 project submissions and submission items

Formal records of work delivered to Qatar clients.

project_submissions  — header (date, period, status, notes, reviewer)
project_submission_items — line items (activity, quantity, unit)

Revision ID: 0033_project_submissions
Revises: 0032_project_timeline_events
Create Date: 2026-06-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_project_submissions"
down_revision: Union[str, None] = "0032_project_timeline_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_date", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("submitted_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="project_submissions_pkey"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE",
                                name="project_submissions_project_fk"),
        sa.ForeignKeyConstraint(["submitted_by"], ["users.id"], ondelete="RESTRICT",
                                name="project_submissions_submitter_fk"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL",
                                name="project_submissions_reviewer_fk"),
        sa.CheckConstraint("period_end >= period_start",
                           name="project_submissions_period_order"),
    )
    op.create_index("project_submissions_project_idx", "project_submissions", ["project_id"])
    op.create_index("project_submissions_status_idx", "project_submissions", ["status"])

    op.create_table(
        "project_submission_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("activity_type_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_label", sa.Text(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="project_submission_items_pkey"),
        sa.ForeignKeyConstraint(["submission_id"], ["project_submissions.id"],
                                ondelete="CASCADE",
                                name="project_submission_items_submission_fk"),
        sa.ForeignKeyConstraint(["activity_type_id"], ["activity_types.id"],
                                ondelete="SET NULL",
                                name="project_submission_items_activity_fk"),
        sa.CheckConstraint("quantity > 0", name="project_submission_items_qty_pos"),
    )
    op.create_index("project_submission_items_submission_idx",
                    "project_submission_items", ["submission_id"])


def downgrade() -> None:
    op.drop_index("project_submission_items_submission_idx")
    op.drop_table("project_submission_items")
    op.drop_index("project_submissions_status_idx")
    op.drop_index("project_submissions_project_idx")
    op.drop_table("project_submissions")
