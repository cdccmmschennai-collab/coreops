"""0079 report origin

Phase 3B step 1 - database representation only, no behaviour change.

Adds daily_work_reports.origin: which distinguishes an employee-created report
from a future system-generated one (auto weekend/holiday/leave reports, not
yet implemented). Every report created before this migration was authored by
an employee, so the column backfills to 'employee' for 100% of existing rows
via server_default - no data is inspected, guessed, or migrated.

Additive only: new enum type report_origin (employee, auto) + one NOT NULL
column with a server default. Nothing reads or writes 'auto' yet - no
generation job, no reconciliation, no editability change, no frontend badge.
Those are separate, later phases.

Revision ID: 0079_report_origin
Revises: 0078_project_code_nullable
Create Date: 2026-08-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0079_report_origin"
down_revision: Union[str, None] = "0078_project_code_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REPORT_ORIGINS = ("employee", "auto")


def upgrade() -> None:
    report_origin = postgresql.ENUM(
        *REPORT_ORIGINS, name="report_origin", create_type=False
    )
    report_origin.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "daily_work_reports",
        sa.Column(
            "origin",
            report_origin,
            nullable=False,
            server_default=sa.text("'employee'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("daily_work_reports", "origin")
    postgresql.ENUM(name="report_origin").drop(op.get_bind(), checkfirst=True)
