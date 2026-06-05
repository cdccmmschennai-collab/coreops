"""0017 work report task project snapshot

Adds project_name, project_code, and project_job_code_code to
work_report_tasks so historical reports remain self-contained.

Before this migration, project display required a live RBAC-scoped lookup
against the projects table.  That lookup fails when the project is archived,
deleted, or the employee loses membership—causing "—" to appear in report
views.

These three columns are populated at task-write time (create/update) so the
displayed values are frozen at the moment the report was saved.  Existing rows
are backfilled from a JOIN against projects and job_codes; rows whose project
has been hard-deleted remain NULL and the UI falls back to "—".

Revision ID: 0017_work_report_task_snapshot
Revises: 0016_notification_target_url
Create Date: 2026-06-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_work_report_task_snapshot"
down_revision: Union[str, None] = "0016_notification_target_url"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("work_report_tasks", sa.Column("project_name", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("project_code", sa.Text(), nullable=True))
    op.add_column("work_report_tasks", sa.Column("project_job_code_code", sa.Text(), nullable=True))

    # Backfill from projects + job_codes for all existing task rows.
    # Rows whose project has been hard-deleted are left NULL.
    op.execute("""
        UPDATE work_report_tasks t
        SET
            project_name         = p.name,
            project_code         = p.code,
            project_job_code_code = jc.code
        FROM projects p
        LEFT JOIN job_codes jc ON jc.id = p.job_code_id
        WHERE t.project_id = p.id
    """)


def downgrade() -> None:
    op.drop_column("work_report_tasks", "project_job_code_code")
    op.drop_column("work_report_tasks", "project_code")
    op.drop_column("work_report_tasks", "project_name")
