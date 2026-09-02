"""Leave classification: Normal or Special.

ONE RULE
========
A leave request is NORMAL when it costs 3 working days or fewer, and SPECIAL
when it costs more::

    working_days <= 3  ->  Normal
    working_days >  3  ->  Special

That is the entire classification. CoreOps no longer has Casual / Sick / Annual
/ Comp Off / Unpaid leave: the employee no longer picks a category, because the
category is not an opinion - it is what the dates already say.

DERIVED, NEVER STORED
=====================
The classification is a pure function of the AUTHORITATIVE working-day count -
the same number `leave/effects.py::leave_working_days` produces from
`calendar/working_days.py`, which an approval charges against and Leave Detail
displays. Nothing here re-implements the office week, and nothing persists the
answer:

  * a stored classification would go stale the moment a request's dates were
    edited, or the moment a company holiday was declared inside its range;
  * every historical request is classified correctly the first time it is read,
    with no backfill and no row rewritten.

`working_days` is a CALENDAR-RESOLVED count, so a leave spanning a weekend is
classified on what it really costs: 29 Aug 2026 - 1 Sep 2026 is 4 working days
(the 5th Saturday works, the Sunday does not) and is therefore Special, even
though only two of its days are weekdays.

This module is pure - no database, no session - so the rule can be tested on
its own, and so there is exactly one place the threshold lives.
"""
from __future__ import annotations

import enum

# The largest number of working days that is still ordinary leave. A request of
# exactly this many days is Normal; one more day makes it Special.
NORMAL_MAX_WORKING_DAYS = 3


class LeaveClassification(str, enum.Enum):
    normal = "normal"
    special = "special"


# Display names, used wherever the classification is shown to a person - the
# email detail line, and (via the frontend's own copy) the leave tables.
CLASSIFICATION_LABELS: dict[LeaveClassification, str] = {
    LeaveClassification.normal: "Normal Leave",
    LeaveClassification.special: "Special Leave",
}


def classify_leave(working_days: int) -> LeaveClassification:
    """Normal for `working_days` <= 3, Special above that.

    `working_days` must be the authoritative count from
    `effects.leave_working_days` - never `(end_date - start_date).days + 1`,
    which counts Sundays, 2nd/4th Saturdays and company holidays and would
    classify a Friday-to-Monday leave as Special when it costs two days.
    """
    if working_days <= NORMAL_MAX_WORKING_DAYS:
        return LeaveClassification.normal
    return LeaveClassification.special


def classification_label(classification: LeaveClassification) -> str:
    """Human label for a classification, never the raw enum value."""
    return CLASSIFICATION_LABELS.get(classification, "Leave")
