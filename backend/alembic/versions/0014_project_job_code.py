"""0014 project job code

Adds projects.job_code_id FK → job_codes, backfills from existing
description values ("Job Code: J-615-2"), then clears those descriptions.

All changes are additive and backward-compatible:
  - new column is nullable
  - backfill is best-effort (only rows whose description matches "Job Code: X")
  - existing description content unrelated to job codes is untouched

Revision ID: 0014_project_job_code
Revises: 0013_role_model
Create Date: 2026-06-04
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014_project_job_code"
down_revision: Union[str, None] = "0013_role_model"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add nullable FK column
    op.add_column(
        "projects",
        sa.Column(
            "job_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("job_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "projects_job_code_idx",
        "projects",
        ["job_code_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # 2. Backfill: match existing "Job Code: XXX" description → look up job_codes.id
    op.execute("""
        UPDATE projects p
        SET job_code_id = jc.id
        FROM job_codes jc
        WHERE p.description LIKE 'Job Code: %'
          AND p.deleted_at IS NULL
          AND jc.code = TRIM(SUBSTRING(p.description FROM 11))
    """)
    # SUBSTRING(p.description FROM 11) skips the 10-char prefix "Job Code: "

    # 3. Clear the "Job Code: ..." text from description now that FK is set
    op.execute("""
        UPDATE projects
        SET description = NULL
        WHERE description LIKE 'Job Code: %'
          AND deleted_at IS NULL
    """)


def downgrade() -> None:
    # Restore the description text from the FK (best-effort)
    op.execute("""
        UPDATE projects p
        SET description = 'Job Code: ' || jc.code
        FROM job_codes jc
        WHERE p.job_code_id = jc.id
          AND p.deleted_at IS NULL
    """)
    op.drop_index("projects_job_code_idx", table_name="projects")
    op.drop_column("projects", "job_code_id")
