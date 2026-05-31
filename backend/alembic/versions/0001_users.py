"""0001 users — identity baseline

Creates required extensions (pgcrypto, citext — audit F5), the user_role enum,
and the users table with a partial-unique email index and an email-format check.

Revision ID: 0001_users
Revises:
Create Date: 2026-05-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_users"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    op.execute(
        "CREATE TYPE user_role AS ENUM ('admin', 'manager', 'employee', 'viewer')"
    )
    role_enum = postgresql.ENUM(
        "admin", "manager", "employee", "viewer", name="user_role", create_type=False
    )

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("role", role_enum, server_default="employee", nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            r"email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'", name="users_email_format"
        ),
    )
    op.create_index(
        "users_email_uq",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("users_email_uq", table_name="users")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS user_role")
