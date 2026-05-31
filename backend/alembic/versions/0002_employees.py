"""0002 employees

Adds employee_status enum and the employees table (FK to users, self-FK
manager, partial-unique code/work_email/user_id, no-self-manager check).

Revision ID: 0002_employees
Revises: 0001_users
Create Date: 2026-05-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_employees"
down_revision: Union[str, None] = "0001_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE TYPE employee_status AS ENUM ('active', 'on_leave', 'exited')")
    status_enum = postgresql.ENUM(
        "active", "on_leave", "exited", name="employee_status", create_type=False
    )

    op.create_table(
        "employees",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("employee_code", sa.Text(), nullable=False),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("work_email", postgresql.CITEXT(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("department", sa.Text(), nullable=True),
        sa.Column("designation", sa.Text(), nullable=True),
        sa.Column(
            "manager_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("date_of_joining", sa.Date(), nullable=True),
        sa.Column("status", status_enum, server_default="active", nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "manager_id IS NULL OR manager_id <> id", name="employees_no_self_manager"
        ),
    )

    op.create_index(
        "employees_code_uq",
        "employees",
        ["employee_code"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "employees_work_email_uq",
        "employees",
        ["work_email"],
        unique=True,
        postgresql_where=sa.text("work_email IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "employees_user_id_uq",
        "employees",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL AND deleted_at IS NULL"),
    )
    op.create_index(
        "employees_manager_idx",
        "employees",
        ["manager_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "employees_status_idx",
        "employees",
        ["status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("employees_status_idx", table_name="employees")
    op.drop_index("employees_manager_idx", table_name="employees")
    op.drop_index("employees_user_id_uq", table_name="employees")
    op.drop_index("employees_work_email_uq", table_name="employees")
    op.drop_index("employees_code_uq", table_name="employees")
    op.drop_table("employees")
    op.execute("DROP TYPE IF EXISTS employee_status")
