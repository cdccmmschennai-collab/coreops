"""0065 project tag scope foundation

Establishes the persistent data model for estimated project tag scope and its
revision history. Data foundation only: nothing computes progress, validates a
Daily Report or touches benchmarks off these columns in this phase.

Adds to `projects` (all denormalised "current state", derived from the newest
revision row):

  estimated_tag_count   INTEGER NULL   how many tags the project expects.
                                       NULL = not established yet, which is NOT
                                       the same as 0 — 0 is rejected by CHECK.
  tag_scope_status      VARCHAR(20)    PROVISIONAL | BASELINED, NULL until the
                                       first estimate exists. No FINALIZED:
                                       scope can still be revised later.
  tag_scope_revision    INTEGER NOT NULL DEFAULT 0
                                       0 before the first estimate, then 1,2,3.
  tag_scope_updated_at  TIMESTAMPTZ NULL
  tag_scope_updated_by  UUID NULL      plain user id, no FK — matching
                                       projects.created_by / updated_by.

Creates `project_tag_scope_revisions`: the append-only trail (revision,
previous/new count, previous/new status, reason, changed_by, created_at),
shaped after project_planned_date_changes. UNIQUE(project_id, revision) — dense
per project, never globally unique. CASCADE on the project (archiving is a soft
delete, so archiving never removes history); RESTRICT on the user.

Backfill: every existing project — NONE and TAG_BASED alike — gets
estimated_tag_count NULL, tag_scope_status NULL, tag_scope_revision 0 and null
update metadata. Nothing is inferred from benchmarks, Daily Reports, actual
counts, Activity Master, project name or submissions; no project tag total is
fabricated. Projects keep behaving exactly as they do today.

Downgrade drops the history table and the five columns with their constraints,
leaving projects.scope_type (migration 0064) untouched.

Revision ID: 0065_project_tag_scope
Revises: 0064_project_scope_type
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0065_project_tag_scope"
down_revision: Union[str, None] = "0064_project_scope_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- current scope on the project -------------------------------------
    op.add_column("projects", sa.Column("estimated_tag_count", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("tag_scope_status", sa.String(20), nullable=True))
    op.add_column(
        "projects",
        sa.Column(
            "tag_scope_revision",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "projects",
        sa.Column("tag_scope_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column("tag_scope_updated_by", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "projects_estimated_tag_count_positive",
        "projects",
        "estimated_tag_count IS NULL OR estimated_tag_count > 0",
    )
    op.create_check_constraint(
        "projects_tag_scope_status_valid",
        "projects",
        "tag_scope_status IS NULL OR tag_scope_status IN ('PROVISIONAL', 'BASELINED')",
    )
    op.create_check_constraint(
        "projects_tag_scope_revision_non_negative",
        "projects",
        "tag_scope_revision >= 0",
    )

    # --- revision history --------------------------------------------------
    op.create_table(
        "project_tag_scope_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("previous_estimated_tag_count", sa.Integer(), nullable=True),
        sa.Column("new_estimated_tag_count", sa.Integer(), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=True),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "changed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "revision", name="project_tag_scope_revisions_uq"),
        sa.CheckConstraint("revision >= 1", name="project_tag_scope_revisions_revision_positive"),
        sa.CheckConstraint(
            "new_estimated_tag_count > 0",
            name="project_tag_scope_revisions_new_count_positive",
        ),
        sa.CheckConstraint(
            "previous_estimated_tag_count IS NULL OR previous_estimated_tag_count > 0",
            name="project_tag_scope_revisions_prev_count_positive",
        ),
        sa.CheckConstraint(
            "new_status IN ('PROVISIONAL', 'BASELINED')",
            name="project_tag_scope_revisions_new_status_valid",
        ),
        sa.CheckConstraint(
            "previous_status IS NULL OR previous_status IN ('PROVISIONAL', 'BASELINED')",
            name="project_tag_scope_revisions_prev_status_valid",
        ),
    )
    op.create_index(
        "project_tag_scope_revisions_project_idx",
        "project_tag_scope_revisions",
        ["project_id", "revision"],
    )


def downgrade() -> None:
    op.drop_index(
        "project_tag_scope_revisions_project_idx",
        table_name="project_tag_scope_revisions",
    )
    op.drop_table("project_tag_scope_revisions")
    op.drop_constraint("projects_tag_scope_revision_non_negative", "projects", type_="check")
    op.drop_constraint("projects_tag_scope_status_valid", "projects", type_="check")
    op.drop_constraint("projects_estimated_tag_count_positive", "projects", type_="check")
    op.drop_column("projects", "tag_scope_updated_by")
    op.drop_column("projects", "tag_scope_updated_at")
    op.drop_column("projects", "tag_scope_revision")
    op.drop_column("projects", "tag_scope_status")
    op.drop_column("projects", "estimated_tag_count")
