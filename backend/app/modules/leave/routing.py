"""Resolves which project (and therefore which Project Head) a new leave
request routes to, from the employee's Daily Work Report evidence AT THE LEAVE
BOUNDARY.

  leave start_date
        -> the evidence date (see below)
        -> that day's Daily Work Report (work_reports.models.DailyWorkReport)
        -> the DISTINCT project(s) logged on it (work_reports.models.WorkReportTask)
        -> exactly one project  -> route there
           zero, ambiguous (>1), or no report at all -> PM fallback (None)

THE EVIDENCE DATE
=================
Two candidate dates are tried, in order, and the FIRST ONE THAT HAS A REPORT
ROW is the evidence date:

  1. ``start_date`` itself, but only when it is a working day. An employee who
     files their report and then takes the rest of the day off has already told
     us which project they are on; the previous day is not more authoritative
     than that. (report 28 Aug, leave 28 Aug -> that project's Head.)
  2. ``previous_working_day(start_date)``. The normal case: leave filed for days
     the employee has not worked. (report 25 Aug, leave 26-28 Aug -> Head.)

The search stops there. It never walks further back, and there is deliberately
no N-day threshold: an employee whose last report is weeks old has no reliable
project at the leave boundary, so their request goes to the PM (report 28 Aug,
leave 2 Sep -> PM; last report 20 Aug, leave 15 Sep -> PM).

Once a date has a report row, that row decides the outcome by itself — a report
with no tasks, or with two projects on it, resolves to None rather than falling
through to the older day. The report is the answer; an ambiguous answer means
the project cannot be reliably established, which is exactly the PM-fallback
condition.

MULTI-DAY LEAVE
===============
Only the boundary is examined. A 3-day leave does NOT need a report for every
day it covers — one reliable project at ``start_date`` routes the whole request.

A PROJECT HEAD'S OWN LEAVE
==========================
Short-circuited to None before any report is read. A Head's leave is never
routed to a Project Head — not even a different project's Head, and not even
when their own latest report belongs to somebody else's project. The PM is the
authoritative approver for a Head, and a NULL ``routed_project_id`` is what
makes ``service._assert_can_review`` reach exactly that outcome: with no routed
project the only reviewer left is a PM, and the requester still cannot review
themselves.

This module resolves the PROJECT only, once, at submission time, and its
result is stored on `LeaveRequest.routed_project_id`. It never resolves a
Head: which Head (if any) currently owns that project is looked up
separately, at read/notify/approve time, via `app.core.authz` — so a Head
reassignment after this request was filed is always honoured (Phase 1
spec §15), while the historical project itself never changes.

A report's status (draft/submitted/granted) is deliberately NOT checked here:
Daily Work Reports have no approval gate (a submitted report is simply
locked from further edits), so a draft report is not less authoritative
about what the employee actually logged that day.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.calendar.working_days import (
    is_working_day,
    load_calendar_overrides,
    previous_working_day,
)
from app.modules.work_reports.models import DailyWorkReport, WorkReportTask


def _evidence_dates(db: Session, leave_date: date) -> list[date]:
    """The candidate evidence dates, nearest to the leave boundary first.

    ``leave_date`` is offered only when the company calendar says it is a
    working day — a report cannot exist for a day the office was shut, so
    checking one would be a wasted query and, worse, would let a stray row on a
    weekend outrank Friday's real report.
    """
    dates: list[date] = []
    non_working, working_overrides = load_calendar_overrides(db, leave_date, leave_date)
    if is_working_day(
        leave_date, non_working=non_working, working_overrides=working_overrides
    ):
        dates.append(leave_date)
    prev_day = previous_working_day(db, leave_date)
    if prev_day is not None:
        dates.append(prev_day)
    return dates


def resolve_routed_project(
    db: Session, employee_id: uuid.UUID, leave_date: date
) -> uuid.UUID | None:
    """The one project the employee's work-report evidence establishes at the
    leave boundary, or None if it can't be established reliably — in every None
    case the caller falls back to the existing PM approval flow.

    None is returned for: a requester who is themselves a Project Head, no
    report on either evidence date, a report with no tasks, and a report
    spanning more than one project.
    """
    if authz.heads_any_project(db, employee_id):
        return None

    for evidence_date in _evidence_dates(db, leave_date):
        report = db.execute(
            select(DailyWorkReport).where(
                DailyWorkReport.employee_id == employee_id,
                DailyWorkReport.report_date == evidence_date,
            )
        ).scalar_one_or_none()
        if report is None:
            continue
        # A report row exists, so THIS is the evidence date and it decides the
        # outcome alone - an unusable one falls back to the PM rather than
        # reaching past it to an older day.
        project_ids = set(
            db.execute(
                select(WorkReportTask.project_id).where(
                    WorkReportTask.report_id == report.id
                )
            ).scalars()
        )
        return next(iter(project_ids)) if len(project_ids) == 1 else None
    return None
