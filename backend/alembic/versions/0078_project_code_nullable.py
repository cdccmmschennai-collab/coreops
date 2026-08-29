"""0078 project code nullable

A handful of real projects (e.g. a Tag Estimation engagement) begin work before
a permanent project code is assigned. The Project Master previously required
`code` on every row; this migration only widens the column to allow NULL so
such a project can exist with no code at all. Project creation/update
validation is unchanged (still requires a code through the normal API) — this
is purely the storage-level relaxation that lets a project record legitimately
carry no code, however it enters the system. The work-report side fallback
(employee-entered project code per activity, stored on work_report_tasks.
project_code) is implemented separately in work_reports/service.py.

The existing partial-unique index (`projects_code_uq`, WHERE deleted_at IS
NULL) needs no change: Postgres unique indexes already treat NULL as distinct
from every other NULL, so any number of no-code projects can coexist.

Revision ID: 0078_project_code_nullable
Revises: 0077_continuation_report_link
Create Date: 2026-08-29
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0078_project_code_nullable"
down_revision: Union[str, None] = "0077_continuation_report_link"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("projects", "code", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Best-effort: a project left with no code cannot be reversed automatically
    # (there is no permanent code to restore), so any such row is stamped with
    # a placeholder derived from its name, matching the 0015 activity_types
    # precedent, rather than blocking the downgrade outright.
    op.execute(
        "UPDATE projects SET code = 'NOCODE-' || LEFT(UPPER(REPLACE(name, ' ', '-')), 20) "
        "WHERE code IS NULL"
    )
    op.alter_column("projects", "code", existing_type=sa.Text(), nullable=False)
