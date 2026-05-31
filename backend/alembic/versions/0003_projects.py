"""0003 projects

Adds project_status + project_member_role enums, the projects table, and the
project_members join table.

Revision ID: 0003_projects
Revises: 0002_employees
Create Date: 2026-05-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_projects"
down_revision: Union[str, None] = "0002_employees"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE TYPE project_status AS ENUM "
        "('planning', 'active', 'on_hold', 'completed', 'archived')"
    )
    op.execute("CREATE TYPE project_member_role AS ENUM ('lead', 'member')")
    status_enum = postgresql.ENUM(
        "planning", "active", "on_hold", "completed", "archived",
        name="project_status", create_type=False,
    )
    role_enum = postgresql.ENUM(
        "lead", "member", name="project_member_role", create_type=False
    )

    op.create_table(
        "projects",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("client", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", status_enum, server_default="planning", nullable=False),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "end_date IS NULL OR start_date IS NULL OR end_date >= start_date",
            name="projects_dates",
        ),
    )
    op.create_index(
        "projects_code_uq",
        "projects",
        ["code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "projects_status_idx",
        "projects",
        ["status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "project_members",
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
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", role_enum, server_default="member", nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("project_id", "employee_id", name="project_members_uq"),
    )
    op.create_index("project_members_project_idx", "project_members", ["project_id"])
    op.create_index("project_members_employee_idx", "project_members", ["employee_id"])


def downgrade() -> None:
    op.drop_index("project_members_employee_idx", table_name="project_members")
    op.drop_index("project_members_project_idx", table_name="project_members")
    op.drop_table("project_members")
    op.drop_index("projects_status_idx", table_name="projects")
    op.drop_index("projects_code_uq", table_name="projects")
    op.drop_table("projects")
    op.execute("DROP TYPE IF EXISTS project_member_role")
    op.execute("DROP TYPE IF EXISTS project_status")
