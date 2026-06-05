"""0018 employee personal email

Adds a nullable personal_email column to employees. This is an informational
field only — it is never used for authentication or account creation. Existing
employees are unaffected (personal_email remains NULL until provided).

The citext extension already exists (created in 0001), so CITEXT is reused here
for case-insensitive storage consistent with work_email.

Revision ID: 0018_employee_personal_email
Revises: 0017_work_report_task_snapshot
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_employee_personal_email"
down_revision: Union[str, None] = "0017_work_report_task_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("personal_email", postgresql.CITEXT(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("employees", "personal_email")
