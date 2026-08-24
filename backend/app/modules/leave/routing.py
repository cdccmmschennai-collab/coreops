"""Resolves which project (and therefore which Project Head) a new leave
request routes to, from the employee's PREVIOUS WORKING DAY's Daily Work
Report — Phase 1 of leave-approval routing to Project Head.

  leave start_date
        -> previous working day    (calendar.working_days.previous_working_day)
        -> that day's Daily Work Report (work_reports.models.DailyWorkReport)
        -> the DISTINCT project(s) logged on it (work_reports.models.WorkReportTask)
        -> exactly one project  -> route there
           zero, ambiguous (>1), or no report at all -> PM fallback (None)

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

from app.modules.calendar.working_days import previous_working_day
from app.modules.work_reports.models import DailyWorkReport, WorkReportTask


def resolve_routed_project(
    db: Session, employee_id: uuid.UUID, leave_date: date
) -> uuid.UUID | None:
    """The one project the employee logged on their previous working day
    before `leave_date`, or None if it can't be unambiguously determined
    (no working day found, no report, no tasks, or more than one project) —
    in every None case the caller falls back to the existing PM approval flow.
    """
    prev_day = previous_working_day(db, leave_date)
    if prev_day is None:
        return None

    report = db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.employee_id == employee_id,
            DailyWorkReport.report_date == prev_day,
        )
    ).scalar_one_or_none()
    if report is None:
        return None

    project_ids = set(
        db.execute(
            select(WorkReportTask.project_id).where(
                WorkReportTask.report_id == report.id
            )
        ).scalars()
    )
    if len(project_ids) != 1:
        return None
    return next(iter(project_ids))
