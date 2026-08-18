"""Approved permission hours, joined to an attendance date (Phase 12).

THE ONE THING THIS FILE DOES
============================
Answer "how many APPROVED permission hours does this employee hold for this
date?" - read-only, from `permission_requests`, for whoever is presenting an
attendance day.

WHAT IT DELIBERATELY IS NOT
===========================
It is not a second store and not a second balance. There is no new table, no
`attendance_records.permission_hours` column and no cached counter: the answer is
derived from the same rows Phase 11 writes, exactly as `balance.py` derives the
monthly allowance from them. Two derivations of one fact would eventually
disagree, and the one on screen would be the wrong one.

It also decides nothing about attendance. It reports hours; the biometric
presentation layer shows them BESIDE the day's status. `attendance_records`
keeps its own status (`present` stays `present`), and no punch, no boundary and
no worked duration is touched by anything here.

ONLY `approved` COUNTS
======================
`pending` has not been granted, `rejected` was refused, and `cancelled` gave the
hours back - none of the three is an attendance fact, so none of them appears.
That is the whole cancellation behavior too: a cancelled request simply stops
matching this filter, so the day returns to its normal presentation with no
compensating update anywhere. Same reason `balance.CONSUMING_STATUSES` exists,
and the same statuses.

WHY THE HOURS ARE SUMMED
========================
Phase 11's duplicate guard (`service._ACTIVE_STATUSES`) means one employee-day
can hold at most one approved request today, so the sum is almost always just
that request's 1 or 2. It is summed rather than picked because summing is the
honest reduction if that guard is ever relaxed: two approved hours-blocks on one
day would read as `3hr`, never silently as one of them.
"""
from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.permissions.balance import CONSUMING_STATUSES
from app.modules.permissions.models import PermissionRequest


def approved_hours_by_employee_date(
    db: Session,
    *,
    employee_ids: Iterable[uuid.UUID],
    date_from: date,
    date_to: date,
) -> dict[tuple[uuid.UUID, date], int]:
    """Approved permission hours per (employee, date) over an inclusive range.

    ONE query for the whole page, whatever its shape - a month for one employee
    (the calendar) or one day for the roster (the PM review). No per-row lookup
    and no N+1.

    A day with no approved permission is ABSENT from the result rather than
    present with a zero: the caller renders nothing for it, and "0hr" is a claim
    nobody made.
    """
    ids = list(employee_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(
            PermissionRequest.employee_id,
            PermissionRequest.permission_date,
            func.coalesce(func.sum(PermissionRequest.duration_hours), 0),
        )
        .where(
            PermissionRequest.employee_id.in_(ids),
            PermissionRequest.status.in_(CONSUMING_STATUSES),
            PermissionRequest.permission_date >= date_from,
            PermissionRequest.permission_date <= date_to,
        )
        .group_by(PermissionRequest.employee_id, PermissionRequest.permission_date)
    ).all()
    return {
        (employee_id, permission_date): int(hours)
        for employee_id, permission_date, hours in rows
        if hours
    }


def approved_hours_on_date(
    db: Session, *, employee_ids: Iterable[uuid.UUID], on_date: date
) -> dict[uuid.UUID, int]:
    """Approved permission hours for one date, keyed by employee.

    The PM daily-review shape: one day, the whole roster.
    """
    by_pair = approved_hours_by_employee_date(
        db, employee_ids=employee_ids, date_from=on_date, date_to=on_date
    )
    return {employee_id: hours for (employee_id, _day), hours in by_pair.items()}


def approved_hours_for_employee(
    db: Session, *, employee_id: uuid.UUID, date_from: date, date_to: date
) -> dict[date, int]:
    """Approved permission hours for one employee, keyed by date.

    The calendar shape: one employee, a month of days.
    """
    by_pair = approved_hours_by_employee_date(
        db, employee_ids=[employee_id], date_from=date_from, date_to=date_to
    )
    return {day: hours for (_employee_id, day), hours in by_pair.items()}
