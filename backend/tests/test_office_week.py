"""The company office week, and the overrides that bend it.

`calendar/working_days.py::is_working_day` is the single answer to "is the
office open", shared by leave, permissions, the daily-report reminder and
WorkItem due dates. This file pins the rule itself:

    Mon-Fri            working
    1st/3rd/5th Sat    working
    2nd/4th Sat        non-working
    Sun                non-working

plus the two date-specific overrides, whose precedence is unchanged: a declared
`working_day` opens the office whatever the week says, and a holiday closes it.

Every date is pinned. August 2026 is used throughout because it has FIVE
Saturdays - the 1st, 8th, 15th, 22nd and 29th - so each occurrence is
unambiguous and the 5th-Saturday case is real rather than contrived.

    docker exec wms-backend-1 pytest tests/test_office_week.py
"""
from datetime import date

from app.modules.calendar.models import CalendarEvent, CalendarEventType
from app.modules.calendar.working_days import (
    is_working_day,
    load_calendar_overrides,
    saturday_occurrence,
)

# The five Saturdays of August 2026, in order.
SAT_1ST = date(2026, 8, 1)
SAT_2ND = date(2026, 8, 8)
SAT_3RD = date(2026, 8, 15)
SAT_4TH = date(2026, 8, 22)
SAT_5TH = date(2026, 8, 29)

SUNDAYS = [date(2026, 8, d) for d in (2, 9, 16, 23, 30)]

MON = date(2026, 8, 24)
TUE = date(2026, 8, 25)
WED = date(2026, 8, 26)
THU = date(2026, 8, 27)
FRI = date(2026, 8, 28)

EMPTY: set[date] = set()


def _open(day: date, *, non_working=EMPTY, working_overrides=EMPTY) -> bool:
    return is_working_day(
        day, non_working=set(non_working), working_overrides=set(working_overrides)
    )


def _event(db, *, event_date: date, event_type: str) -> CalendarEvent:
    ev = CalendarEvent(
        event_date=event_date,
        title="Test",
        event_type=CalendarEventType(event_type),
    )
    db.add(ev)
    db.commit()
    db.refresh(ev)
    return ev


def _open_in_db(db, day: date) -> bool:
    """The real path: load the day's overrides from the calendar, then rule."""
    non_working, working_overrides = load_calendar_overrides(db, day, day)
    return is_working_day(
        day, non_working=non_working, working_overrides=working_overrides
    )


# ── the dates are what this file claims they are ────────────────────────────

def test_the_pinned_dates_are_the_weekdays_they_are_named_for():
    for sat in (SAT_1ST, SAT_2ND, SAT_3RD, SAT_4TH, SAT_5TH):
        assert sat.weekday() == 5, sat
    for sun in SUNDAYS:
        assert sun.weekday() == 6, sun
    assert [MON.weekday(), TUE.weekday(), WED.weekday(), THU.weekday(),
            FRI.weekday()] == [0, 1, 2, 3, 4]


def test_saturday_occurrence_counts_from_the_day_of_month():
    assert saturday_occurrence(SAT_1ST) == 1
    assert saturday_occurrence(SAT_2ND) == 2
    assert saturday_occurrence(SAT_3RD) == 3
    assert saturday_occurrence(SAT_4TH) == 4
    assert saturday_occurrence(SAT_5TH) == 5


# ── the office week ─────────────────────────────────────────────────────────

def test_first_saturday_is_working():
    assert _open(SAT_1ST)


def test_second_saturday_is_non_working():
    assert not _open(SAT_2ND)


def test_third_saturday_is_working():
    assert _open(SAT_3RD)


def test_fourth_saturday_is_non_working():
    assert not _open(SAT_4TH)


def test_fifth_saturday_is_working():
    """The case that started this change: 29 August 2026 is a 5th Saturday, so a
    28-31 August leave range covers three working days, not two."""
    assert _open(SAT_5TH)


def test_sunday_is_always_non_working():
    for sun in SUNDAYS:
        assert not _open(sun), sun


def test_monday_to_friday_are_working():
    for day in (MON, TUE, WED, THU, FRI):
        assert _open(day), day


# ── overrides: precedence is unchanged ──────────────────────────────────────

def test_a_holiday_on_a_working_saturday_closes_it():
    """A 1st Saturday is an ordinary working day, and a declared holiday closes
    it exactly as it closes a weekday."""
    assert not _open(SAT_1ST, non_working={SAT_1ST})


def test_a_working_day_override_opens_a_non_working_saturday():
    """The company declares a particular 2nd Saturday working."""
    assert _open(SAT_2ND, working_overrides={SAT_2ND})


def test_a_holiday_on_a_normal_friday_closes_it():
    assert not _open(FRI, non_working={FRI})


def test_a_working_day_override_opens_a_sunday():
    assert _open(SUNDAYS[0], working_overrides={SUNDAYS[0]})


def test_a_working_day_override_still_beats_a_holiday_on_the_same_date():
    """Unchanged precedence: `working_day` is the declared inverse of a holiday
    and wins over every other signal."""
    assert _open(FRI, non_working={FRI}, working_overrides={FRI})


# ── the same rules through the real calendar table ──────────────────────────

def test_calendar_events_drive_the_rule_end_to_end(db):
    """`load_calendar_overrides` feeds `is_working_day` the same two sets the
    pure tests above build by hand."""
    # Untouched dates follow the office week.
    assert _open_in_db(db, SAT_1ST)
    assert not _open_in_db(db, SAT_2ND)
    assert _open_in_db(db, FRI)

    _event(db, event_date=SAT_1ST, event_type="holiday")
    _event(db, event_date=SAT_2ND, event_type="working_day")
    _event(db, event_date=FRI, event_type="cdc_holiday")

    assert not _open_in_db(db, SAT_1ST)
    assert _open_in_db(db, SAT_2ND)
    assert not _open_in_db(db, FRI)


def test_an_informational_event_changes_nothing(db):
    """`event` is informational only - it must not close the office."""
    _event(db, event_date=MON, event_type="event")
    assert _open_in_db(db, MON)
