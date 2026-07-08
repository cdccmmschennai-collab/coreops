"""0055 reconcile project_members with current assignments

One-time data reconciliation. `member_count` is COUNT(project_members), and the
visibility backbone was only reference-counted on removal from 2026-07-08 onward
(see _prune_project_member). Rows orphaned *before* that fix - people removed
from their last activity, or prior Heads replaced/cleared - were left behind, so
member_count over-counted.

This migration reconciles project_members to exactly {project Head} UNION
{distinct current activity assignees} for every project:
  - DELETE rows that are neither the Head nor a current activity assignee.
  - INSERT any missing Head / activity-assignee rows (defensive; idempotent).

After this, member_count equals the number of unique people currently assigned,
matching what /activity-staffing returns and the Members card shows. The service
layer keeps the two tables in sync going forward via _ensure_project_member /
_prune_project_member.

Note: this treats "project member" as Head + activity assignee, which is how the
product defines it. Any row added directly via the legacy POST /projects/{id}/
members endpoint (not used by the frontend) that has no matching Head/activity
assignment is also removed.

Revision ID: 0055_reconcile_project_members
Revises: 0054_project_activity_members
Create Date: 2026-07-08
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0055_reconcile_project_members"
down_revision: Union[str, None] = "0054_project_activity_members"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Remove stale rows: not the project Head and not on any activity.
    op.execute(
        """
        DELETE FROM project_members pm
        USING projects p
        WHERE pm.project_id = p.id
          AND (p.head_employee_id IS NULL OR pm.employee_id <> p.head_employee_id)
          AND NOT EXISTS (
              SELECT 1 FROM project_activity_members am
              WHERE am.project_id = pm.project_id
                AND am.employee_id = pm.employee_id
          )
        """
    )

    # 2) Backfill any missing Head visibility rows.
    op.execute(
        """
        INSERT INTO project_members (project_id, employee_id, role)
        SELECT p.id, p.head_employee_id, 'contributor'::project_member_role
        FROM projects p
        WHERE p.head_employee_id IS NOT NULL
        ON CONFLICT (project_id, employee_id) DO NOTHING
        """
    )

    # 3) Backfill any missing activity-assignee visibility rows.
    op.execute(
        """
        INSERT INTO project_members (project_id, employee_id, role)
        SELECT DISTINCT am.project_id, am.employee_id, 'contributor'::project_member_role
        FROM project_activity_members am
        ON CONFLICT (project_id, employee_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Irreversible data cleanup - the deleted stale rows carried no information
    # worth restoring (they no longer corresponded to any assignment).
    pass
