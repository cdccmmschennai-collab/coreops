"""Derived submission-deadline state for a deliverable (ADR-003 Amendment 2).

Pure and side-effect free: the state is computed at read time from the stored
`target_date` + `status` and the business date, and is NEVER persisted. The
stored status stays `planned | completed` on purpose - the leave-review
Deliverable Impact check selects `status == planned`, and an extra stored value
such as "overdue" would silently drop rows out of it.

Ladder (days_remaining = target_date - today, in Asia/Kolkata):

    completed     status is completed (whatever the date)
    no_deadline   no target date
    overdue       days_remaining < 0
    due_today     days_remaining == 0
    urgent        days_remaining == 1
    due_soon      2 <= days_remaining <= REMINDER_WINDOW_DAYS
    on_track      days_remaining >  REMINDER_WINDOW_DAYS
"""
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from app.modules.project_deliverables.models import DeliverableStatus

# Same business calendar and constant name as leave / permissions / weekly report.
BUSINESS_TZ = ZoneInfo("Asia/Kolkata")

# Reminders start this many days before the deadline (inclusive).
REMINDER_WINDOW_DAYS = 5

DeadlineState = Literal[
    "completed",
    "no_deadline",
    "overdue",
    "due_today",
    "urgent",
    "due_soon",
    "on_track",
]


def business_today() -> date:
    """Today in the company's business timezone - never the server's local date
    (the containers run in UTC, which is a day behind IST before 05:30)."""
    return datetime.now(BUSINESS_TZ).date()


def days_remaining(
    target_date: date | None, status: DeliverableStatus, today: date
) -> int | None:
    """Signed calendar days until the deadline (0 = due today, negative =
    overdue). None when there is no deadline or the deliverable is completed -
    a countdown is meaningless for either."""
    if target_date is None or status == DeliverableStatus.completed:
        return None
    return (target_date - today).days


def deadline_state(
    target_date: date | None, status: DeliverableStatus, today: date
) -> DeadlineState:
    if status == DeliverableStatus.completed:
        return "completed"
    if target_date is None:
        return "no_deadline"
    days = (target_date - today).days
    if days < 0:
        return "overdue"
    if days == 0:
        return "due_today"
    if days == 1:
        return "urgent"
    if days <= REMINDER_WINDOW_DAYS:
        return "due_soon"
    return "on_track"
