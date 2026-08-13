"""Daily biometric summary - first IN and last OUT, pure functions.

No database, no writes, no ORM. Everything here takes timestamps and returns
timestamps, so the rule below is testable in isolation and cannot drift from
whatever the query layer happens to do.

WHY THIS IS AN ANCHOR RULE, NOT AN IN/OUT CLASSIFIER
====================================================
EasyTime, in THIS deployment, carries no punch direction. Measured over the
370-punch backfill (46 codes, 3 days):

  * `punch_state` is the string "0" on every single row - zero variance
  * `punch_state_display` is empty on every row
  * one terminal only (F22/ID / CK5T224960376), so there is no
    IN-reader / OUT-reader split either
  * `is_attendance` is NULL, `purpose` is a constant 9

So no per-punch IN/OUT label can be derived, and odd/even pairing is not merely
unproven, it is DISPROVEN: 24 of 109 employee-days carry an ODD punch count
(1, 3, 5, 7, 9 and 13-punch days all occur), which "odd = IN, even = OUT" would
mis-classify outright.

What CAN be established without direction is the OUTER BOUNDARY of a person's
day: the first time they were seen and the last time they were seen. That is
what `first_in` and `last_out` mean here, and it is an explicitly approved
assumption rather than a device fact. It is deliberately NOT called
check_in/check_out, and it never reaches `attendance_records`.

If EasyTime ever emits real punch states, this module is the only place that has
to change.

THE RULE
========
1. Sort the day's punches ascending. Input order is never trusted - late
   uploads and backfills arrive out of order.
2. Collapse re-scans: keep a punch only when it is at least
   DEDUP_WINDOW_SECONDS after the last KEPT punch. A person tapping three times
   in nine seconds (real: code 187 at 10:43:20 / :28 / :34) is one event, not
   three. Comparing against the last KEPT punch rather than the previous raw one
   means a long burst collapses to a single punch instead of ratcheting forward.
3. `first_in` = the first surviving punch.
4. `last_out` = the last surviving punch, and ONLY when at least two punches
   survive. One surviving punch is one sighting: it cannot be both an arrival
   and a departure, so `last_out` stays None. An OUT is never invented.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

# A tap and its immediate repeats are one event. 60s is above the observed
# re-scan cluster (real gaps of 3-22 seconds) and far below any real
# out-and-back-again, the shortest of which in the backfill is many minutes.
DEDUP_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class DaySummary:
    """One employee, one attendance day.

    `punch_count` is every raw punch (debugging: it is what the operations view
    shows); `kept` is what survived re-scan collapsing. When the counts differ,
    duplicates were filtered.

    `kept` carries the actual surviving instants, not just a count, so a human
    reviewer can be shown the punches the boundary was taken FROM. That is the
    whole point of a derived boundary: it has to be checkable.
    """

    first_in: datetime | None
    last_out: datetime | None
    punch_count: int
    kept: tuple[datetime, ...] = ()

    @property
    def kept_count(self) -> int:
        return len(self.kept)


EMPTY_DAY = DaySummary(None, None, 0, ())


def collapse_rescans(
    times: Iterable[datetime], *, window_seconds: int = DEDUP_WINDOW_SECONDS
) -> list[datetime]:
    """Sort ascending and drop repeats inside `window_seconds` of the last kept.

    Never mutates its input and never raises on an empty or single-item input.
    """
    ordered = sorted(times)
    kept: list[datetime] = []
    for t in ordered:
        if kept and (t - kept[-1]).total_seconds() < window_seconds:
            continue
        kept.append(t)
    return kept


def summarize_day(
    times: Iterable[datetime], *, window_seconds: int = DEDUP_WINDOW_SECONDS
) -> DaySummary:
    """Outer boundary of one employee-day. See the module docstring for the rule."""
    raw = list(times)
    if not raw:
        return EMPTY_DAY

    kept = collapse_rescans(raw, window_seconds=window_seconds)
    # A single sighting cannot be both an arrival and a departure.
    last_out = kept[-1] if len(kept) >= 2 else None
    return DaySummary(
        first_in=kept[0],
        last_out=last_out,
        punch_count=len(raw),
        kept=tuple(kept),
    )
