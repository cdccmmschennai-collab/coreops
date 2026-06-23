"""0045 deliverable planned start date + change history

Adds the change-tracking layer to deliverables:

- Add `planned_start_date` (nullable Date) to project_deliverables so the
  deliverable timeline carries Created / Planned Start / Due / Actual
  Completion dates.
- Create `deliverable_changes`, an append-only audit trail of every tracked
  edit (planned start date, due date, status reversal). Each row records the
  field changed, old/new values, the user who made the change, a mandatory
  reason, and a timestamp. Mirrors project_planned_date_changes (0031).

Revision ID: 0045_deliverable_changes
Revises: 0044_project_planning_plant
Create Date: 2026-06-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0045_deliverable_changes"
down_revision: Union[str, None] = "0044_project_planning_plant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "project_deliverables",
        sa.Column("planned_start_date", sa.Date(), nullable=True),
    )

    op.create_table(
        "deliverable_changes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("deliverable_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="deliverable_changes_pkey"),
        sa.ForeignKeyConstraint(
            ["deliverable_id"],
            ["project_deliverables.id"],
            ondelete="CASCADE",
            name="deliverable_changes_deliverable_fk",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["users.id"],
            ondelete="RESTRICT",
            name="deliverable_changes_user_fk",
        ),
    )
    op.create_index(
        "deliverable_changes_deliverable_idx",
        "deliverable_changes",
        ["deliverable_id"],
    )


def downgrade() -> None:
    op.drop_index("deliverable_changes_deliverable_idx")
    op.drop_table("deliverable_changes")
    op.drop_column("project_deliverables", "planned_start_date")
