"""Working-day resolution against the company calendar.

The baseline working week is Mon-Fri. Entries in ``company_calendar_events``
override that baseline:

  * ``holiday`` / ``cdc_holiday`` / ``natural_hazard`` make an otherwise normal
    weekday NON-working.
  * ``working_day`` marks a normally-off day (Saturday, Sunday, or a day that is
    also flagged as a holiday) as working. It is the declared inverse of a
    holiday, so it wins over every other signal.
  * ``event`` is informational only and never changes whether the office works.

The date arithmetic is a pure function (:func:`is_working_day`) so it can be
tested without a database; :func:`load_calendar_overrides` is the only part that
touches SQL.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.calendar.models import CalendarEvent, CalendarEventType

# Calendar entries that close the office.
NON_WORKING_EVENT_TYPES = (
    CalendarEventType.holiday,
    CalendarEventType.cdc_holiday,
    CalendarEventType.natural_hazard,
)

# How far back a search is willing to walk before giving up. A gap this long
# means the calendar is misconfigured, not that the office was really shut.
DEFAULT_MAX_LOOKBACK_DAYS = 30


def is_working_day(
    day: date, *, non_working: set[date], working_overrides: set[date]
) -> bool:
    """Whether ``day`` is a working day, given the calendar overrides.

    Pure: pass the two sets from :func:`load_calendar_overrides` (or build them
    directly in a test).
    """
    if day in working_overrides:
        return True
    if day in non_working:
        return False
    return day.weekday() < 5  # Mon..Fri


def load_calendar_overrides(
    db: Session, date_from: date, date_to: date
) -> tuple[set[date], set[date]]:
    """``(non_working_dates, working_day_overrides)`` in the inclusive range."""
    rows = db.execute(
        select(CalendarEvent.event_date, CalendarEvent.event_type).where(
            CalendarEvent.event_date >= date_from,
            CalendarEvent.event_date <= date_to,
        )
    ).all()
    non_working: set[date] = set()
    working_overrides: set[date] = set()
    for event_date, event_type in rows:
        if event_type in NON_WORKING_EVENT_TYPES:
            non_working.add(event_date)
        elif event_type == CalendarEventType.working_day:
            working_overrides.add(event_date)
    return non_working, working_overrides


def previous_working_day(
    db: Session,
    reference: date,
    *,
    max_lookback_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> date | None:
    """The most recent working day strictly before ``reference``.

    Walks backwards day by day, honouring weekends and the company calendar, and
    returns the first working day it finds. Returns ``None`` if there is no
    working day within ``max_lookback_days`` (a misconfigured calendar), so the
    caller can bail out instead of looping forever.
    """
    earliest = reference - timedelta(days=max_lookback_days)
    cursor = reference - timedelta(days=1)
    non_working, working_overrides = load_calendar_overrides(db, earliest, cursor)
    while cursor >= earliest:
        if is_working_day(
            cursor, non_working=non_working, working_overrides=working_overrides
        ):
            return cursor
        cursor -= timedelta(days=1)
    return None


def next_working_day(
    db: Session,
    reference: date,
    *,
    max_lookahead_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> date | None:
    """The first working day strictly after ``reference``. Forward mirror of
    :func:`previous_working_day`. Returns ``None`` if none is found within
    ``max_lookahead_days`` (a misconfigured calendar)."""
    latest = reference + timedelta(days=max_lookahead_days)
    cursor = reference + timedelta(days=1)
    non_working, working_overrides = load_calendar_overrides(db, cursor, latest)
    while cursor <= latest:
        if is_working_day(
            cursor, non_working=non_working, working_overrides=working_overrides
        ):
            return cursor
        cursor += timedelta(days=1)
    return None


def add_working_days(
    db: Session,
    start: date,
    steps: int,
    *,
    max_lookahead_days: int = DEFAULT_MAX_LOOKBACK_DAYS,
) -> date | None:
    """``start`` plus ``steps`` WORKING days (``start`` itself is never counted
    as a step: ``steps=0`` returns ``start`` unchanged). Used for WorkItem due
    dates: ``due = add_working_days(db, started_on, target_days - 1)``, so a
    1-day allowed duration is due the same day it starts, and a 2-day duration
    is due the next WORKING day (weekends/company holidays skipped).

    Returns ``None`` if it cannot resolve within ``max_lookahead_days`` extra
    days beyond the naive count (a misconfigured calendar) — the caller
    decides the fallback.
    """
    if steps <= 0:
        return start
    latest = start + timedelta(days=max_lookahead_days + steps)
    non_working, working_overrides = load_calendar_overrides(db, start, latest)
    cursor = start
    remaining = steps
    while remaining > 0 and cursor <= latest:
        cursor += timedelta(days=1)
        if is_working_day(
            cursor, non_working=non_working, working_overrides=working_overrides
        ):
            remaining -= 1
    return cursor if remaining == 0 else None
