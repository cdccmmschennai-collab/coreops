"""0064 project scope type

Adds projects.scope_type — whether a project takes part in Project Tag Scope
functionality at all:

  NONE       not a tag-based project (TOOL DEVELOPMENT, TRAINING, INTERNAL
             DEVELOPMENT, ...). Behaves exactly as every project does today.
  TAG_BASED  participates in Project Tag Scope. Later phases hang estimated
             tags, revisions and progress off this classification.

Purely additive and backward-compatible:

- NOT NULL with server_default 'NONE', so every existing project — including
  every live engineering project — is backfilled to NONE and keeps its current
  behaviour bit-for-bit. Nothing is inspected, guessed or promoted to
  TAG_BASED; that is always an explicit human edit on the Project Edit page.
- The server default also keeps existing INSERT paths working unchanged
  (project master import, seed scripts, any client that does not send the
  field).
- VARCHAR(20) + CHECK rather than a native Postgres enum, following the
  activity_master.access_type / benchmark_type / benchmark_exception_code
  precedent — adding a third classification later is an ALTER of one
  constraint, not an enum type migration.

No behaviour reads this column yet: Daily Reports, benchmarks, Activity Master
and the exports are untouched by this migration and by this phase. No tag count
column is added here.

Downgrade drops the constraint and the column; no other column is touched, so
the only thing lost is the classification itself.

Revision ID: 0064_project_scope_type
Revises: 0063_benchmark_exception_code
Create Date: 2026-08-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0064_project_scope_type"
down_revision: Union[str, None] = "0063_benchmark_exception_code"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "scope_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'NONE'"),
        ),
    )
    op.create_check_constraint(
        "projects_scope_type_valid",
        "projects",
        "scope_type IN ('NONE', 'TAG_BASED')",
    )


def downgrade() -> None:
    op.drop_constraint("projects_scope_type_valid", "projects", type_="check")
    op.drop_column("projects", "scope_type")
