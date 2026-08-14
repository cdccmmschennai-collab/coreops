"""Phase 7: worked duration + conservative attendance classification. Pure.

No database, no ORM, no FastAPI, no HTTP. This module takes a Phase 6 day
boundary plus a contracted shift and returns numbers and a verdict, so every
rule below is directly unit-testable and cannot drift from whatever the query
layer happens to do.

WHAT THIS LAYER IS FOR
======================
Phase 6 answers "when was this person first and last seen?". That is evidence.
It is NOT an answer to "what attendance does this day represent?", and the gap
between the two is where attendance systems normally go wrong: the tempting rule
is "a punch exists, therefore present", which credits a 09:10-only day and a
full 09:00-17:30 day identically.

So this layer measures, and then refuses to decide anything it cannot establish
objectively:

  * it computes how long the person was on site (last_out - first_in);
  * it compares that against the employee's CONTRACTED shift window, which is
    CoreOps' own data (`offices.shift_start` / `shift_end`, migration 0007);
  * it marks a day `present` ONLY when that comparison objectively settles it;
  * everything else is handed to a human with a reason code attached.

WHAT IT DELIBERATELY REFUSES TO DO
==================================
It never invents a CAUSE. Biometric evidence cannot distinguish a half day from
approved permission, from an early release, from a forgotten punch - all four
produce the same short duration. So `half_day`, `permission`, `leave` and
`absent` appear nowhere in this module, and a short day, an afternoon-only day
and a no-punch day are all reported as unresolved rather than interpreted. Cause
belongs to the leave/permission integration and to the human review that comes
after it.

It never invents a PUNCH either. One surviving punch stays one sighting: no OUT
is synthesized from the shift end, so a person seen once at 09:15 is `incomplete`
and not "worked until 17:30".

And it computes ONE session, not many. `first_in -> last_out` elapsed time is
the whole duration rule. The middle punches of a nine-punch day are shown to a
reviewer (Phase 6 already returns them) but they are not treated as session
boundaries: EasyTime reports no punch direction in this deployment, so pairing
them would be a guess about which trips were lunch and which were exits. Break
deduction, overtime, night shifts and cross-midnight shifts are likewise absent -
each one needs a policy answer that does not exist yet.

THE OPEN POLICY ITEMS THIS LAYER WORKS AROUND
=============================================
From docs/attendance/attendance-policy-open-decisions.md: O-1 (required daily
duration), O-2 (does the lunch break count as worked time), O-3 (late-arrival
grace period), O-4 (expected shift end). None are answered. Rather than pick
values, this module compares against the scheduled WINDOW with a grace of
`SHORTFALL_GRACE_MINUTES` (currently 0) and routes anything short to review. When
management answers O-1 and O-3, this file and that one constant are what change.

A NOTE ON TIMEZONES
===================
The scheduled window is built in the SHIFT's own timezone, because
`offices.shift_start` is a local TIME interpreted against `offices.timezone`
(offices/models.py). The attendance DAY, however, is bucketed by Phase 6 in
`ATTENDANCE_TIMEZONE` (Asia/Kolkata) for every employee. For a Chennai office
those agree, which is every punch currently in the system. For an office in a
different zone - the Qatar row exists - they would not, and reconciling that is a
real decision (whose midnight starts an attendance day?) that has not been made.
It is recorded here rather than silently resolved.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.modules.biometric.constants import (
    BLOCKING_REVIEW_REASONS,
    CLASSIFICATION_INCOMPLETE,
    CLASSIFICATION_NEEDS_REVIEW,
    CLASSIFICATION_NO_RECORD,
    CLASSIFICATION_PRESENT,
    DEFAULT_SHIFT_END,
    DEFAULT_SHIFT_START,
    REASON_DEFAULT_SHIFT_ASSUMED,
    REASON_EARLY_LAST_PUNCH,
    REASON_LATE_FIRST_PUNCH,
    REASON_MISSING_SECOND_PUNCH,
    REASON_NO_BIOMETRIC_RECORD,
    REASON_SHIFT_TIMEZONE_INVALID,
    REASON_SHIFT_UNKNOWN,
    REASON_SHORT_OF_SCHEDULED,
    REASON_UNSUPPORTED_SHIFT_WINDOW,
    SHIFT_SOURCE_DEFAULT,
    SHIFT_SOURCE_OFFICE,
    SHORTFALL_GRACE_MINUTES,
)
from app.modules.biometric.summary import DaySummary


@dataclass(frozen=True)
class Shift:
    """One employee's contracted window, as configured - never as measured.

    `source` records whether this came from the employee's office row or from the
    module fallback, so a reader can tell a real comparison from an assumed one.
    `break_minutes` is carried for display and is NOT deducted anywhere (O-2).
    """

    start: time
    end: time
    timezone: str
    break_minutes: int | None = None
    source: str = SHIFT_SOURCE_OFFICE

    @classmethod
    def default(cls, *, timezone_name: str) -> "Shift":
        """The fallback for an employee with no office. See DEFAULT_SHIFT_START."""
        return cls(
            start=DEFAULT_SHIFT_START,
            end=DEFAULT_SHIFT_END,
            timezone=timezone_name,
            break_minutes=None,
            source=SHIFT_SOURCE_DEFAULT,
        )


@dataclass(frozen=True)
class DayClassification:
    """What Phase 7 can say about one employee-day, and nothing more.

    `worked_minutes` is None whenever both boundaries do not exist - not 0. Zero
    would read as "was here for no time", which is a measurement; None is the
    truth, which is "not measurable from this evidence".

    `reasons` is ordered most-decisive first so a UI can show `reasons[0]` alone
    and still say something useful.
    """

    classification: str
    review_required: bool
    reasons: tuple[str, ...]

    first_in: datetime | None
    last_out: datetime | None
    worked_minutes: int | None

    scheduled_start_at: datetime | None
    scheduled_end_at: datetime | None
    scheduled_minutes: int | None
    shift_source: str | None


def worked_minutes(first_in: datetime | None, last_out: datetime | None) -> int | None:
    """Whole minutes on site: last_out - first_in. One session, by design.

    None (never 0) when either boundary is missing, and None for a negative span:
    Phase 6 draws both ends from one sorted list so it cannot produce one, which
    means a negative value is a bug elsewhere and reporting "0h 00m" would bury
    it.

    Truncated, not rounded, so a reported duration is never longer than the time
    actually observed.
    """
    if first_in is None or last_out is None:
        return None
    seconds = (last_out - first_in).total_seconds()
    if seconds < 0:
        return None
    return int(seconds // 60)


def scheduled_window(
    day: date, shift: Shift | None
) -> tuple[datetime | None, datetime | None, int | None, str | None]:
    """The contracted window for one calendar day as two instants and a length.

    Returns `(start_at, end_at, minutes, problem_reason)`; `problem_reason` is
    None when the window is usable. Three things can go wrong, and each is
    reported rather than guessed around:

      * no shift configured at all -> nothing to compare against;
      * a bad IANA timezone on the office row -> refuse rather than assume UTC,
        which would shift a contracted 09:00 by hours;
      * end at or before start -> that is a night/cross-midnight shift, which
        Phase 7 does not implement. It is NOT silently wrapped to the next day.
    """
    if shift is None:
        return None, None, None, REASON_SHIFT_UNKNOWN

    try:
        tz = ZoneInfo(shift.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None, None, None, REASON_SHIFT_TIMEZONE_INVALID

    if shift.end <= shift.start:
        return None, None, None, REASON_UNSUPPORTED_SHIFT_WINDOW

    start_at = datetime.combine(day, shift.start, tzinfo=tz)
    end_at = datetime.combine(day, shift.end, tzinfo=tz)
    minutes = int((end_at - start_at).total_seconds() // 60)
    # Normalized to UTC like every other timestamp CoreOps returns, so a consumer
    # never has to handle two different offset conventions in one response.
    return (
        start_at.astimezone(timezone.utc),
        end_at.astimezone(timezone.utc),
        minutes,
        None,
    )


def classify_day(
    summary: DaySummary,
    *,
    day: date,
    shift: Shift | None,
    grace_minutes: int = SHORTFALL_GRACE_MINUTES,
) -> DayClassification:
    """One employee-day: duration plus the most conservative honest verdict.

    The decision tree, in full:

      no first_in            -> no_record    (NOT absent - the reason may be
                                              leave, a holiday, or a device that
                                              did not record them)
      first_in, no last_out  -> incomplete   (one sighting; no OUT is invented)
      both, worked + grace
        >= scheduled         -> present      (objectively a complete day)
      both, anything else    -> needs_review (measured, not settled - and no
                                              cause is attached to it)

    `reasons` also collects observations that do not open a review by themselves
    (late first punch, early last punch, an assumed shift), because a reviewer
    reading a `present` day still benefits from knowing it started at 09:10.
    """
    first_in = summary.first_in
    last_out = summary.last_out
    minutes = worked_minutes(first_in, last_out)

    start_at, end_at, scheduled_minutes, window_problem = scheduled_window(day, shift)
    shift_source = shift.source if shift is not None else None

    reasons: list[str] = []

    # ── the decisive reason, first ──────────────────────────────────────────
    if first_in is None:
        classification = CLASSIFICATION_NO_RECORD
        reasons.append(REASON_NO_BIOMETRIC_RECORD)
    elif last_out is None:
        classification = CLASSIFICATION_INCOMPLETE
        reasons.append(REASON_MISSING_SECOND_PUNCH)
    elif scheduled_minutes is None or minutes is None:
        # Measured, but with nothing trustworthy to measure it against.
        classification = CLASSIFICATION_NEEDS_REVIEW
    elif minutes + grace_minutes >= scheduled_minutes:
        classification = CLASSIFICATION_PRESENT
    else:
        classification = CLASSIFICATION_NEEDS_REVIEW
        reasons.append(REASON_SHORT_OF_SCHEDULED)

    # A broken or missing shift window is decisive for a two-punch day and
    # context for any other, so it is recorded either way.
    if window_problem is not None:
        reasons.append(window_problem)

    # ── observations: context, never a verdict on their own ─────────────────
    if start_at is not None and first_in is not None and first_in > start_at:
        reasons.append(REASON_LATE_FIRST_PUNCH)
    if end_at is not None and last_out is not None and last_out < end_at:
        reasons.append(REASON_EARLY_LAST_PUNCH)
    if shift is not None and shift.source == SHIFT_SOURCE_DEFAULT:
        reasons.append(REASON_DEFAULT_SHIFT_ASSUMED)

    return DayClassification(
        classification=classification,
        # Derived from the reasons rather than set per branch, so "what opens a
        # review" is defined in exactly one place (BLOCKING_REVIEW_REASONS) and a
        # new reason cannot be added without deciding which kind it is.
        review_required=any(r in BLOCKING_REVIEW_REASONS for r in reasons),
        reasons=tuple(reasons),
        first_in=first_in,
        last_out=last_out,
        worked_minutes=minutes,
        scheduled_start_at=start_at,
        scheduled_end_at=end_at,
        scheduled_minutes=scheduled_minutes,
        shift_source=shift_source,
    )
