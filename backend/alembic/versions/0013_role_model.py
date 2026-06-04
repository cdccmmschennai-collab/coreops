"""0013 role model

Revised role model:
  System roles: project_manager (full access), employee (basic user)
  Project roles: team_lead, contributor, qc (inside project_members only)

  DB changes:
    - user_role enum: ADD project_manager
    - project_member_role enum: ADD team_lead, contributor, qc
    - CREATE TABLE project_managers
    - ALTER TABLE employees ADD COLUMN reporting_pm_id
    - Data migration: admin/manager → project_manager; viewer → employee
    - Data migration: lead → team_lead; member → contributor
    - Backfill project_managers from project.created_by
    - Backfill employees.reporting_pm_id from manager_id chain

  Old enum values (admin, manager, viewer, lead, member) are kept in PostgreSQL
  until cleanup migration 0018. No existing data is lost.

Revision ID: 0013_role_model
Revises: 0013_enum_expansion
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013_role_model"
down_revision: Union[str, None] = "0013_enum_expansion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enum values were added in 0013_enum_expansion (committed separately).
    # This migration handles tables, columns, and data migrations only.

    # ── 1. project_managers join table ───────────────────────────────────────
    op.create_table(
        "project_managers",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("project_id", "user_id", name="project_managers_uq"),
    )
    op.create_index("project_managers_project_idx", "project_managers", ["project_id"])
    op.create_index("project_managers_user_idx", "project_managers", ["user_id"])

    # ── 3. employees.reporting_pm_id ─────────────────────────────────────────
    op.add_column(
        "employees",
        sa.Column(
            "reporting_pm_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "employees_reporting_pm_idx",
        "employees",
        ["reporting_pm_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 4. Data migration: system roles ──────────────────────────────────────
    # admin and manager → project_manager
    op.execute(
        "UPDATE users SET role = 'project_manager'::user_role "
        "WHERE role IN ('admin', 'manager')"
    )
    # viewer → employee
    op.execute(
        "UPDATE users SET role = 'employee'::user_role WHERE role = 'viewer'"
    )

    # ── 5. Data migration: project member roles ───────────────────────────────
    op.execute(
        "UPDATE project_members SET role = 'team_lead'::project_member_role "
        "WHERE role = 'lead'"
    )
    op.execute(
        "UPDATE project_members SET role = 'contributor'::project_member_role "
        "WHERE role = 'member'"
    )

    # ── 6. Backfill project_managers from project.created_by ─────────────────
    op.execute("""
        INSERT INTO project_managers (project_id, user_id)
        SELECT p.id, p.created_by
        FROM projects p
        JOIN users u ON u.id = p.created_by
        WHERE p.created_by IS NOT NULL
          AND p.deleted_at IS NULL
        ON CONFLICT (project_id, user_id) DO NOTHING
    """)

    # ── 7. Backfill reporting_pm_id from manager_id chain ────────────────────
    # For each employee, find the user_id of their manager_id employee.
    # Only backfill when that manager's user is now a project_manager.
    op.execute("""
        UPDATE employees e
        SET reporting_pm_id = mgr.user_id
        FROM employees mgr
        JOIN users u ON u.id = mgr.user_id
        WHERE e.manager_id IS NOT NULL
          AND e.manager_id = mgr.id
          AND mgr.user_id IS NOT NULL
          AND mgr.deleted_at IS NULL
          AND e.deleted_at IS NULL
          AND u.role = 'project_manager'
    """)


def downgrade() -> None:
    # Remove backfilled columns and tables.
    # Enum values added by ADD VALUE cannot be removed without a full type rebuild;
    # they are dropped in the cleanup migration 0018.
    op.drop_index("employees_reporting_pm_idx", table_name="employees")
    op.drop_column("employees", "reporting_pm_id")

    op.drop_index("project_managers_user_idx", table_name="project_managers")
    op.drop_index("project_managers_project_idx", table_name="project_managers")
    op.drop_table("project_managers")

    # Reverse data migration — restore best-effort (user.role only, cannot distinguish
    # original admin vs manager; both become admin for safety on rollback)
    op.execute(
        "UPDATE users SET role = 'admin'::user_role WHERE role = 'project_manager'"
    )
    op.execute(
        "UPDATE project_members SET role = 'lead'::project_member_role "
        "WHERE role = 'team_lead'"
    )
    op.execute(
        "UPDATE project_members SET role = 'member'::project_member_role "
        "WHERE role IN ('contributor', 'qc')"
    )
