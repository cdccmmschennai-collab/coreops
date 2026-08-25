"""next_working_day / add_working_days — forward counterparts to
previous_working_day, added for WorkItem's working-day due-date math
(Phase 2 lump-sum continuation approval)."""
from datetime import date

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.working_days import add_working_days, next_working_day


def _event(db, *, event_date, event_type):
    ev = CalendarEvent(event_date=event_date, title="Test", event_type=CalendarEventType(event_type))
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def test_next_working_day_plain_weekday(db):
    # Mon 2026-07-13 -> Tue 2026-07-14
    assert next_working_day(db, date(2026, 7, 13)) == date(2026, 7, 14)


def test_next_working_day_skips_weekend(db):
    # Fri 2026-07-10 -> Mon 2026-07-13
    assert date(2026, 7, 10).weekday() == 4
    assert next_working_day(db, date(2026, 7, 10)) == date(2026, 7, 13)


def test_next_working_day_skips_holiday(db):
    _event(db, event_date=date(2026, 7, 14), event_type="holiday")
    assert next_working_day(db, date(2026, 7, 13)) == date(2026, 7, 15)


def test_next_working_day_honours_working_override(db):
    # A declared working Saturday counts even though it's a weekend.
    assert date(2026, 7, 11).weekday() == 5  # Saturday
    _event(db, event_date=date(2026, 7, 11), event_type="working_day")
    assert next_working_day(db, date(2026, 7, 10)) == date(2026, 7, 11)


def test_add_working_days_zero_returns_start(db):
    assert add_working_days(db, date(2026, 7, 13), 0) == date(2026, 7, 13)


def test_add_working_days_one_plain(db):
    assert add_working_days(db, date(2026, 7, 13), 1) == date(2026, 7, 14)


def test_add_working_days_skips_weekend(db):
    # Fri 2026-07-10 + 1 working day -> Mon 2026-07-13.
    assert add_working_days(db, date(2026, 7, 10), 1) == date(2026, 7, 13)


def test_add_working_days_skips_weekend_and_holiday(db):
    # Fri 2026-07-10 + 2 working days: Sat/Sun skipped, Mon is a holiday too
    # -> Wed 2026-07-15.
    _event(db, event_date=date(2026, 7, 13), event_type="holiday")
    assert add_working_days(db, date(2026, 7, 10), 2) == date(2026, 7, 15)
