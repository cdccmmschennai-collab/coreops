"""0013 enum expansion

Adds new role values to user_role and project_member_role.
Must be its own migration because ALTER TYPE ADD VALUE cannot be used
in the same transaction as DML that references the new values (psycopg3 / PG16).
After this migration commits, 0013b can safely UPDATE rows using the new values.

Revision ID: 0013_enum_expansion
Revises: 0012_master_data
Create Date: 2026-06-04
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0013_enum_expansion"
down_revision: Union[str, None] = "0012_master_data"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'project_manager'")
    op.execute("ALTER TYPE project_member_role ADD VALUE IF NOT EXISTS 'team_lead'")
    op.execute("ALTER TYPE project_member_role ADD VALUE IF NOT EXISTS 'contributor'")
    op.execute("ALTER TYPE project_member_role ADD VALUE IF NOT EXISTS 'qc'")


def downgrade() -> None:
    # PostgreSQL cannot remove enum values once committed.
    # Old values are cleaned up in migration 0018.
    pass
