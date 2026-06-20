"""0043 task due date = assigned day

Benchmark/TASK_BASED activities are daily production work, so a row's due_date
should default to the assigned (report) date rather than being pushed a day
forward. The service formula changed from started + period to
started + (period - 1); every existing due_date was therefore stored exactly one
day too late. Shift them all back by one day to match.

Only TASK_BASED rows carry a due_date (NUMERIC rows leave it NULL), so the
WHERE due_date IS NOT NULL guard scopes this correctly. The shift is a uniform
-1 day regardless of period (old = started+period, new = started+period-1).

Revision ID: 0043_task_due_date_assigned_day
Revises: 0042_calendar_event_categories
Create Date: 2026-06-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0043_task_due_date_assigned_day"
down_revision: Union[str, None] = "0042_calendar_event_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE work_report_tasks "
        "SET due_date = due_date - INTERVAL '1 day' "
        "WHERE due_date IS NOT NULL"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE work_report_tasks "
        "SET due_date = due_date + INTERVAL '1 day' "
        "WHERE due_date IS NOT NULL"
    )
