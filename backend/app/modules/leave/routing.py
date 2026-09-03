"""Resolves which project (and therefore which Project Head) a new leave
request routes to, from the employee's Daily Work Report evidence.

  leave start_date
        -> search BACKWARD through working days for the latest valid report
        -> that report's Daily Work Report (work_reports.models.DailyWorkReport)
        -> the DISTINCT project(s) logged on it (work_reports.models.WorkReportTask)
        -> exactly one project  -> route there
           ambiguous (>1 project), or no valid report at all -> PM fallback (None)

THE BACKWARD SEARCH
===================
The search starts at ``start_date`` and walks backwards through WORKING DAYS
until it finds the employee's latest VALID work report. It is deliberately NOT
``start_date - 1 calendar day`` and it is deliberately not a single step:

  * Non-working days are skipped, per the company calendar
    (``calendar.working_days``): weekends, the 2nd/4th Saturday, declared
    holidays, and any day a ``working_day`` override re-opens. A report filed on
    a day the office was shut is not evidence - Monday's leave routes off
    FRIDAY's report, never off a stray Sunday one.
  * Working days with no report, and working days whose only report logged no
    project work at all, are skipped too, and the search keeps going. A week of
    leave, a comp-off or a company shutdown does not erase which project the
    employee is on; it just means the answer is further back.

``start_date`` itself is the first candidate, but only when the calendar says it
is a working day. An employee who filed their report and then took the rest of
the day off has already told us which project they are on, and that is the most
recent evidence there is. (report 28 Aug, leave 28 Aug -> that project's Head.)

There is NO staleness window. The rule is "the project the employee most
recently worked on", so an employee whose last report is three weeks old still
routes to that project's current Head; only an employee with no usable report
at all falls back to the PM.

WHAT MAKES A REPORT "VALID"
===========================
A report row on a working day that logs AT LEAST ONE project task. A report with
zero task rows names no project, so it cannot establish one - and zero-task
reports are ordinary, not exceptional: every no-activity day (leave, week_off,
company_holiday, comp_off) has one, including the ones
``work_reports.auto_reports`` generates automatically for weekends and for leave
already granted. Treating those as the answer would send an employee returning
from one leave to the PM on their next request, which is exactly the silent
mis-route this resolver exists to prevent.

A report's status (draft/submitted/granted) is deliberately NOT checked: Daily
Work Reports have no approval gate (a submitted report is simply locked from
further edits), so a draft report is not less authoritative about what the
employee actually logged that day. Its ``origin`` is not checked either - an
automatic report that DOES carry project tasks is as true as a typed one.

AMBIGUITY STOPS THE SEARCH
==========================
Once a valid report is found it decides the outcome ALONE. A report spanning two
projects resolves to None (the PM) rather than reaching further back for a
cleaner one: it is real evidence about where the employee was, it just does not
name one project, and picking either of them - or an older, superseded one -
would be a guess. The PM fallback is the defined answer for "the project cannot
be established", and a guess is never allowed to stand in for it.

MULTI-DAY LEAVE
===============
Only the start date is examined. A 3-day leave does NOT need a report for every
day it covers - one reliable project at ``start_date`` routes the whole request.

A PROJECT HEAD'S OWN LEAVE
==========================
Short-circuited to None before any report is read. A Head's leave is never
routed to a Project Head - not even a different project's Head, and not even
when their own latest report belongs to somebody else's project. The PM is the
authoritative approver for a Head, and a NULL ``routed_project_id`` is what
makes ``service._assert_can_review`` reach exactly that outcome: with no routed
project the only reviewer left is a PM, and the requester still cannot review
themselves.

This module resolves the PROJECT only, once, at submission time, and its
result is stored on `LeaveRequest.routed_project_id`. It never resolves a
Head: which Head (if any) currently owns that project is looked up
separately, at read/notify/approve time, via `app.core.authz` - so a Head
reassignment after this request was filed is always honoured (Phase 1
spec §15), while the historical project itself never changes. A project with no
current Head resolves to no Head there, and the request falls back to the
existing PM / reporting-manager chain in `leave/recipients.py` - this module has
no say in that and does not duplicate it.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import authz
from app.modules.calendar.working_days import is_working_day, load_calendar_overrides
from app.modules.work_reports.models import DailyWorkReport, WorkReportTask

# How many candidate reports the backward walk will examine before giving up.
# The walk is driven by the reports that actually exist, so it normally stops on
# the first one; this bound only matters for a pathological history of nothing
# but non-working-day reports, and exhausting it yields the ordinary PM fallback
# rather than a wrong project. It is NOT a staleness window - a single report
# from months ago is still found on the first row.
MAX_EVIDENCE_REPORTS = 60


def _latest_valid_report_id(
    db: Session, employee_id: uuid.UUID, boundary: date
) -> uuid.UUID | None:
    """The employee's latest work report at-or-before ``boundary`` that lands on
    a working day and logs at least one project task, or None.

    The candidates are the reports that EXIST, newest first - which is the same
    walk as "step back one working day at a time, skipping days with no report",
    without issuing a query per empty day. Days the office was shut are then
    dropped by the calendar, so a report filed on a Sunday never outranks the
    Friday one before it.
    """
    candidates = db.execute(
        select(DailyWorkReport.id, DailyWorkReport.report_date)
        .where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date <= boundary,
            select(WorkReportTask.id)
            .where(WorkReportTask.report_id == DailyWorkReport.id)
            .exists(),
        )
        .order_by(DailyWorkReport.report_date.desc())
        .limit(MAX_EVIDENCE_REPORTS)
    ).all()
    if not candidates:
        return None

    non_working, working_overrides = load_calendar_overrides(
        db, candidates[-1].report_date, boundary
    )
    for report_id, report_date in candidates:
        if is_working_day(
            report_date, non_working=non_working, working_overrides=working_overrides
        ):
            return report_id
    return None


def resolve_routed_project(
    db: Session, employee_id: uuid.UUID, leave_date: date
) -> uuid.UUID | None:
    """The one project the employee's work-report evidence establishes, or None
    if it can't be established reliably - in every None case the caller falls
    back to the existing PM approval flow.

    None is returned for: a requester who is themselves a Project Head, no valid
    report anywhere at or before the leave boundary, and a valid report spanning
    more than one project.
    """
    if authz.heads_any_project(db, employee_id):
        return None

    report_id = _latest_valid_report_id(db, employee_id, leave_date)
    if report_id is None:
        return None
    # This report IS the evidence and it decides alone - an ambiguous one falls
    # back to the PM rather than reaching past it to an older day.
    project_ids = set(
        db.execute(
            select(WorkReportTask.project_id).where(
                WorkReportTask.report_id == report_id
            )
        ).scalars()
    )
    return next(iter(project_ids)) if len(project_ids) == 1 else None
