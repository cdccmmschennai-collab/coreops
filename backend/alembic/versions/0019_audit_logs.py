"""0019 audit_logs

Adds the audit_logs table: an append-only trail of security-sensitive actions
(auth, user/role/password changes, account linkage, employee lifecycle, project
membership). Rows are immutable — only created_at is tracked. actor_email /
actor_role are denormalized snapshots so entries survive user purges. The
actor FK uses ON DELETE SET NULL as a defensive measure (users are soft-deleted
in practice).

Revision ID: 0019_audit_logs
Revises: 0018_employee_personal_email
Create Date: 2026-06-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_audit_logs"
down_revision: Union[str, None] = "0018_employee_personal_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_email", sa.String(320), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default=sa.text("'success'")
        ),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.create_index("audit_created_idx", "audit_logs", [sa.text("created_at DESC")])
    op.create_index(
        "audit_actor_idx", "audit_logs", ["actor_user_id", "created_at"]
    )
    op.create_index(
        "audit_entity_idx", "audit_logs", ["entity_type", "entity_id"]
    )
    op.create_index("audit_action_idx", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("audit_action_idx", table_name="audit_logs")
    op.drop_index("audit_entity_idx", table_name="audit_logs")
    op.drop_index("audit_actor_idx", table_name="audit_logs")
    op.drop_index("audit_created_idx", table_name="audit_logs")
    op.drop_table("audit_logs")
