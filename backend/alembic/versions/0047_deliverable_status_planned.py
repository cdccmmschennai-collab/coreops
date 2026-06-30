"""0047 deliverable status: planned/completed

Collapses the deliverable_status enum from three values to two:

  pending      -> planned
  in_progress  -> planned
  completed    -> completed (unchanged)

Postgres has no "remove enum value" primitive, so the type is rebuilt: a new
two-value enum is created, the column is re-typed with a CASE mapping, the old
type is dropped, and the new one is renamed back to deliverable_status. The
default also moves from 'pending' to 'planned'.

deliverable_changes rows that recorded a status transition (field='status')
still hold the old textual values 'pending'/'in_progress' in old/new_value;
those are remapped to 'planned' so the timeline reads consistently.

Revision ID: 0047_deliverable_status_planned
Revises: 0046_employee_leave_balances
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0047_deliverable_status_planned"
down_revision: Union[str, None] = "0046_employee_leave_balances"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE project_deliverables ALTER COLUMN status DROP DEFAULT")
    op.execute("CREATE TYPE deliverable_status_new AS ENUM ('planned', 'completed')")
    op.execute(
        """
        ALTER TABLE project_deliverables
            ALTER COLUMN status TYPE deliverable_status_new
            USING (
                CASE status::text
                    WHEN 'completed' THEN 'completed'
                    ELSE 'planned'
                END::deliverable_status_new
            )
        """
    )
    op.execute("DROP TYPE deliverable_status")
    op.execute("ALTER TYPE deliverable_status_new RENAME TO deliverable_status")
    op.execute(
        "ALTER TABLE project_deliverables ALTER COLUMN status SET DEFAULT 'planned'"
    )

    # Remap historical status-change rows to the new vocabulary.
    op.execute(
        """
        UPDATE deliverable_changes
           SET old_value = 'planned'
         WHERE field = 'status' AND old_value IN ('pending', 'in_progress')
        """
    )
    op.execute(
        """
        UPDATE deliverable_changes
           SET new_value = 'planned'
         WHERE field = 'status' AND new_value IN ('pending', 'in_progress')
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE project_deliverables ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "CREATE TYPE deliverable_status_old AS ENUM ('pending', 'in_progress', 'completed')"
    )
    # 'planned' has no faithful inverse; map it back to 'pending'.
    op.execute(
        """
        ALTER TABLE project_deliverables
            ALTER COLUMN status TYPE deliverable_status_old
            USING (
                CASE status::text
                    WHEN 'completed' THEN 'completed'
                    ELSE 'pending'
                END::deliverable_status_old
            )
        """
    )
    op.execute("DROP TYPE deliverable_status")
    op.execute("ALTER TYPE deliverable_status_old RENAME TO deliverable_status")
    op.execute(
        "ALTER TABLE project_deliverables ALTER COLUMN status SET DEFAULT 'pending'"
    )
    op.execute(
        """
        UPDATE deliverable_changes
           SET new_value = 'pending'
         WHERE field = 'status' AND new_value = 'planned'
        """
    )
    op.execute(
        """
        UPDATE deliverable_changes
           SET old_value = 'pending'
         WHERE field = 'status' AND old_value = 'planned'
        """
    )
