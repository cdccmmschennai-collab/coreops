"""0048 day_status taxonomy

Replaces the original Google-Form day_status placeholders with the company's
real day-status taxonomy (12 values). Postgres has no "remove enum value"
primitive, so the type is rebuilt: a new enum is created, the column is
re-typed with a CASE mapping from the old values, the old type is dropped, and
the new one is renamed back to day_status.

Old -> new mapping (best-effort for any pre-existing reports):

  on_leave    -> leave
  half_day    -> leave            (no faithful match; treated as non-working)
  on_duty     -> work_at_office
  office      -> work_at_office
  wfh         -> work_from_home
  permission  -> permission_first_half_1hr
  comp_off    -> comp_off         (unchanged)

NULL day_status stays NULL.

Revision ID: 0048_day_status_taxonomy
Revises: 0047_deliverable_status_planned
Create Date: 2026-06-30
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0048_day_status_taxonomy"
down_revision: Union[str, None] = "0047_deliverable_status_planned"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_VALUES = (
    "leave",
    "company_holiday",
    "work_from_home",
    "week_off",
    "work_at_office",
    "comp_off",
    "overtime_compensation",
    "overtime_salary",
    "permission_first_half_1hr",
    "permission_second_half_1hr",
    "permission_first_half_2hr",
    "permission_second_half_2hr",
)


def upgrade() -> None:
    values = ", ".join(f"'{v}'" for v in _NEW_VALUES)
    op.execute(f"CREATE TYPE day_status_new AS ENUM ({values})")
    op.execute(
        """
        ALTER TABLE daily_work_reports
            ALTER COLUMN day_status TYPE day_status_new
            USING (
                CASE day_status::text
                    WHEN 'on_leave'   THEN 'leave'
                    WHEN 'half_day'   THEN 'leave'
                    WHEN 'on_duty'    THEN 'work_at_office'
                    WHEN 'office'     THEN 'work_at_office'
                    WHEN 'wfh'        THEN 'work_from_home'
                    WHEN 'permission' THEN 'permission_first_half_1hr'
                    WHEN 'comp_off'   THEN 'comp_off'
                    ELSE NULL
                END::day_status_new
            )
        """
    )
    op.execute("DROP TYPE day_status")
    op.execute("ALTER TYPE day_status_new RENAME TO day_status")


def downgrade() -> None:
    op.execute(
        "CREATE TYPE day_status_old AS ENUM "
        "('on_duty', 'office', 'half_day', 'on_leave', 'wfh', 'permission', 'comp_off')"
    )
    # New values have no faithful inverse; map them to the closest legacy value.
    op.execute(
        """
        ALTER TABLE daily_work_reports
            ALTER COLUMN day_status TYPE day_status_old
            USING (
                CASE day_status::text
                    WHEN 'leave'           THEN 'on_leave'
                    WHEN 'company_holiday' THEN 'on_leave'
                    WHEN 'week_off'        THEN 'on_leave'
                    WHEN 'comp_off'        THEN 'comp_off'
                    WHEN 'work_from_home'  THEN 'wfh'
                    WHEN 'work_at_office'  THEN 'office'
                    WHEN 'overtime_compensation' THEN 'office'
                    WHEN 'overtime_salary'       THEN 'office'
                    WHEN 'permission_first_half_1hr'  THEN 'permission'
                    WHEN 'permission_second_half_1hr' THEN 'permission'
                    WHEN 'permission_first_half_2hr'  THEN 'permission'
                    WHEN 'permission_second_half_2hr' THEN 'permission'
                    ELSE NULL
                END::day_status_old
            )
        """
    )
    op.execute("DROP TYPE day_status")
    op.execute("ALTER TYPE day_status_old RENAME TO day_status")
