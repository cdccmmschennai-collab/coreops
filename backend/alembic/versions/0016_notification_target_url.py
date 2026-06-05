"""0016 notification target url

Adds target_url column to notifications for deep-link navigation.
Null for historical rows; new notifications carry a URL so the frontend
can route the user directly to the related record on click.

Revision ID: 0016_notification_target_url
Revises: 0015_activity_type_optional_code
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_notification_target_url"
down_revision: Union[str, None] = "0015_activity_type_optional_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("notifications", sa.Column("target_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("notifications", "target_url")
