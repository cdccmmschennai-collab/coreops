"""0042 calendar event categories

Extends calendar_event_type with the categories the Company Calendar needs:
  - cdc_holiday    company-specific (CDC) holiday
  - natural_hazard unplanned closure (cyclone/flood/etc.)
  - working_day    office OPEN on a normally-off day (2nd/4th Sat, Sunday,
                   or a declared holiday) — the inverse of a holiday

Existing 'holiday' and 'event' values are unchanged. PostgreSQL 12+ permits
ALTER TYPE ... ADD VALUE inside a transaction as long as the new value is not
used in the same transaction (we only add them here), so no COMMIT hack is
needed. Removing enum values isn't supported by Postgres, so downgrade is a
documented no-op.

Revision ID: 0042_calendar_event_categories
Revises: 0041_work_report_task_plant
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0042_calendar_event_categories"
down_revision: Union[str, None] = "0041_work_report_task_plant"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_VALUES = ("cdc_holiday", "natural_hazard", "working_day")


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE calendar_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum type. Leaving the added
    # values in place is harmless; rows using them would need to be remapped
    # before the type could be rebuilt, which we don't do automatically.
    pass
