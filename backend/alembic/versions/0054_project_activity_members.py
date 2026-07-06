"""0054 project activity members

Phase 3 (Activity Assignment Layer) - Task 1. Adds the per-activity staffing
join table the Head manages: exactly one Lead per activity (partial-unique
index), many Contributors, and QC as an additive boolean flag (never a
standalone role value).

Design: docs/superpowers/specs/2026-07-05-coreops-hierarchy-redesign-design.md
(SS4.1). `activity_id` references activity_master; the service layer (Task 3)
enforces that it points at a level='activity' node. Additive and backward-
compatible; no existing table is touched. APIs, authz wiring, and the UI land
in later Phase-3 tasks.

Revision ID: 0054_project_activity_members
Revises: 0053_project_head
Create Date: 2026-07-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0054_project_activity_members"
down_revision: Union[str, None] = "0053_project_head"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE project_activity_member_role AS ENUM ('lead', 'contributor')")
    role_enum = postgresql.ENUM(
        "lead", "contributor", name="project_activity_member_role", create_type=False
    )

    op.create_table(
        "project_activity_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Activity node in activity_master. RESTRICT: never orphan a staffing row
        # by deleting the master activity. Service enforces level='activity'.
        sa.Column(
            "activity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("activity_master.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", role_enum, nullable=False),
        # Additive QC responsibility; may be true on a lead or a contributor.
        sa.Column("is_qc", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        # One assignment (hence one base role) per person per activity per project.
        sa.UniqueConstraint(
            "project_id", "activity_id", "employee_id", name="project_activity_members_uq"
        ),
    )

    # At most one Lead per (project, activity). Contributors are unconstrained here.
    op.create_index(
        "project_activity_members_one_lead_uq",
        "project_activity_members",
        ["project_id", "activity_id"],
        unique=True,
        postgresql_where=sa.text("role = 'lead'"),
    )
    op.create_index(
        "project_activity_members_project_idx", "project_activity_members", ["project_id"]
    )
    op.create_index(
        "project_activity_members_activity_idx", "project_activity_members", ["activity_id"]
    )
    op.create_index(
        "project_activity_members_employee_idx", "project_activity_members", ["employee_id"]
    )
    op.create_index(
        "project_activity_members_project_activity_idx",
        "project_activity_members",
        ["project_id", "activity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "project_activity_members_project_activity_idx", table_name="project_activity_members"
    )
    op.drop_index(
        "project_activity_members_employee_idx", table_name="project_activity_members"
    )
    op.drop_index(
        "project_activity_members_activity_idx", table_name="project_activity_members"
    )
    op.drop_index(
        "project_activity_members_project_idx", table_name="project_activity_members"
    )
    op.drop_index(
        "project_activity_members_one_lead_uq", table_name="project_activity_members"
    )
    op.drop_table("project_activity_members")
    op.execute("DROP TYPE IF EXISTS project_activity_member_role")
