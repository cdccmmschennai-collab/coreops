"""0070 project production status

Creates `project_production_statuses`: the append-only trail of production
status updates a Project Head or an Activity Lead records for a
(project, revision, activity) combination.

Columns:

  id             UUID PK, gen_random_uuid()
  project_id     UUID NOT NULL -> projects.id ON DELETE CASCADE
  revision       TEXT NOT NULL   user-entered document revision ("REV-0"). Held
                                 here, never copied onto the project - one
                                 project carries many revisions at once.
  activity_id    UUID NOT NULL -> activity_master.id ON DELETE RESTRICT
                                 (level='activity'; enforced in the service,
                                 which also requires the activity to be staffed
                                 on the project). No duplicate activity table.
  status         VARCHAR(20) NOT NULL, CHECK IN ('in_progress', 'closed') -
                                 the same two literals project_activities
                                 already uses for these states.
  tag_count      INTEGER NOT NULL DEFAULT 0
  doc_count      INTEGER NOT NULL DEFAULT 0
  spares_count   INTEGER NOT NULL DEFAULT 0
  crs_count      INTEGER NOT NULL DEFAULT 0
                                 Four independent units, never one generic
                                 "count"; NOT NULL DEFAULT 0 + a non-negative
                                 CHECK, matching work_report_tasks' per-unit
                                 counts.
  completed_on   DATE NULL
  remarks        TEXT NULL
  created_by     UUID NOT NULL -> users.id ON DELETE RESTRICT - the real
                                 person who made the update. The role is
                                 deliberately not stored.
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()

Append-only by construction: no updated_at, no deleted_at, and no application
path that updates or deletes a row. An INPROGRESS -> CLOSED change inserts a
second row, so both remain auditable; the "current" status is derived as the
newest created_at per project+revision+activity.

Indexes (two, matching the module's only two access paths):
  ..._project_revision_activity_idx  (project_id, revision, activity_id,
                                      created_at DESC)  -> latest + history for
                                      one project+revision+activity
  ..._project_activity_created_idx   (project_id, activity_id, created_at DESC)
                                      -> history for one project+activity
                                      across revisions

New table only: no existing table, column or row is touched, so no production
data is modified. Downgrade drops the table (and with it its indexes and
constraints), returning the schema exactly to 0069.

Revision ID: 0070_project_production_status
Revises: 0069_leave_allocation_ledger
Create Date: 2026-08-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0070_project_production_status"
down_revision: Union[str, None] = "0069_leave_allocation_ledger"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_production_statuses",
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
        sa.Column("revision", sa.Text(), nullable=False),
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activity_master.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("tag_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("doc_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("spares_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("crs_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
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
        sa.CheckConstraint(
            "status IN ('in_progress', 'closed')",
            name="project_production_statuses_status_valid",
        ),
        sa.CheckConstraint(
            "btrim(revision) <> ''",
            name="project_production_statuses_revision_not_blank",
        ),
        sa.CheckConstraint(
            "tag_count >= 0 AND doc_count >= 0 AND spares_count >= 0 AND crs_count >= 0",
            name="project_production_statuses_counts_non_negative",
        ),
    )
    op.create_index(
        "project_production_statuses_project_revision_activity_idx",
        "project_production_statuses",
        ["project_id", "revision", "activity_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "project_production_statuses_project_activity_created_idx",
        "project_production_statuses",
        ["project_id", "activity_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "project_production_statuses_project_activity_created_idx",
        table_name="project_production_statuses",
    )
    op.drop_index(
        "project_production_statuses_project_revision_activity_idx",
        table_name="project_production_statuses",
    )
    op.drop_table("project_production_statuses")
