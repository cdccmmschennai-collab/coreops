"""Rework Activity Approval service (migrations 0090 + 0091).

Phase 2 scope: raising requests when a report is SUBMITTED, telling the PM,
and exposing each row's approval state to the report reads. Review (approve /
reject), listing and correction live in later phases.

WHEN A REQUEST IS RAISED
========================
Only inside work_reports.service.submit_work_report, in the SAME transaction as
the submit, via :func:`raise_requests_for_report`. Saving a draft never raises
one, sends nothing, and leaves no link on the row.

For every report row whose sub-activity is CURRENTLY flagged
requires_pm_approval, keyed by (report, day_part, sub_activity):
  * latest cycle PENDING   -> reuse it (no second request, no second email)
  * latest cycle APPROVED  -> keep it (an approved row stays approved)
  * none / REJECTED / CANCELLED -> open a new cycle (cycle_no + 1, linked to
                              the previous one) - history is never rewritten
A pending cycle whose row is no longer on the report is CANCELLED.

Normal (unflagged) rows are untouched: they are submitted exactly as before and
never wait on a rework decision.

WHO IS TOLD
===========
The employee's reporting PM (Employee.reporting_pm_id), else the project's
assigned PMs - the same routing as Activity Requests and the outstanding-report
reminder. Any PM may approve (the existing PM-reviews-everything rule); routing
is a delivery decision only. Notifications run AFTER the submit committed and
never raise.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.employees.models import Employee
from app.modules.projects.models import ProjectManager
from app.modules.rework_approvals.models import ReworkApprovalRequest, ReworkRequestStatus
from app.modules.users.models import User
from app.modules.work_reports.models import (
    DailyWorkReport,
    DayPart,
    ReportMode,
    WorkReportPeriod,
    WorkReportTask,
)

logger = logging.getLogger("coreops.rework_approvals")

DAY_PART_LABEL = {
    DayPart.full_day.value: "Full Day",
    DayPart.first_half.value: "First Half",
    DayPart.second_half.value: "Second Half",
}

# Employee-facing label per request status. "pending" reads "In Review" - one
# name for one state (the spec's REQUESTED and IN REVIEW are the same thing).
STATUS_LABEL = {
    ReworkRequestStatus.pending.value: "In Review",
    ReworkRequestStatus.approved.value: "Approved",
    ReworkRequestStatus.rejected.value: "Rejected",
    ReworkRequestStatus.cancelled.value: "Cancelled",
}


def detail_path(request_id: uuid.UUID) -> str:
    """The in-app detail page for one request - the email and bell destination."""
    return f"/activity-requests/rework/{request_id}"


# ---------- submit-time raising --------------------------------------------

def _day_remarks(report: DailyWorkReport, period: WorkReportPeriod | None) -> str:
    if report.report_mode == ReportMode.split_day.value and period is not None:
        return (period.remarks or "").strip()
    return (report.remarks or "").strip()


def raise_requests_for_report(
    db: Session, actor: User, report: DailyWorkReport
) -> list[ReworkApprovalRequest]:
    """Raise / reuse the approval cycle for every flagged row on `report`, stamp
    each row's rework_request_id, and cancel orphaned pending cycles.

    Returns only the NEWLY created requests (the caller notifies those after its
    commit). Does NOT commit - the submit owns the transaction, so the report
    and its requests land together or not at all. The partial unique index
    rework_requests_one_pending_uq is the final guard against a concurrent
    double submit; the caller turns its IntegrityError into a clean 409.
    """
    rows = db.execute(
        select(WorkReportTask, ActivityMaster)
        .join(ActivityMaster, ActivityMaster.id == WorkReportTask.sub_activity_id)
        .where(WorkReportTask.report_id == report.id)
    ).all()
    periods = {
        p.id: p
        for p in db.execute(
            select(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
        ).scalars()
    }
    existing = list(
        db.execute(
            select(ReworkApprovalRequest)
            .where(ReworkApprovalRequest.report_id == report.id)
            .order_by(ReworkApprovalRequest.cycle_no, ReworkApprovalRequest.requested_at)
        ).scalars()
    )
    latest_by_key: dict[tuple[str, uuid.UUID], ReworkApprovalRequest] = {}
    for req in existing:  # ordered ascending, so the last one wins
        latest_by_key[(req.day_part, req.sub_activity_id)] = req

    live_keys: set[tuple[str, uuid.UUID]] = set()
    created: list[ReworkApprovalRequest] = []
    for row, sub in rows:
        if not sub.requires_pm_approval:
            # A row that no longer needs approval carries no link.
            row.rework_request_id = None
            continue
        period = periods.get(row.period_id) if row.period_id else None
        day_part = period.day_part if period is not None else DayPart.full_day.value
        key = (day_part, sub.id)
        live_keys.add(key)
        latest = latest_by_key.get(key)
        if latest is not None and latest.status in (
            ReworkRequestStatus.pending.value,
            ReworkRequestStatus.approved.value,
        ):
            row.rework_request_id = latest.id
            continue
        req = ReworkApprovalRequest(
            report_id=report.id,
            employee_id=report.employee_id,
            project_id=row.project_id,
            activity_id=sub.parent_id,
            sub_activity_id=sub.id,
            report_date=report.report_date,
            day_part=day_part,
            project_code=row.project_code,
            project_name=row.project_name,
            activity_name=row.activity_name,
            sub_activity_name=row.sub_activity_name or sub.name,
            # The activity's own remark first; the day's remark when it is blank.
            employee_remarks=(row.description or "").strip()
            or _day_remarks(report, period)
            or None,
            status=ReworkRequestStatus.pending.value,
            cycle_no=(latest.cycle_no + 1) if latest is not None else 1,
            previous_request_id=latest.id if latest is not None else None,
            requested_by=actor.id,
        )
        db.add(req)
        db.flush()
        row.rework_request_id = req.id
        latest_by_key[key] = req
        created.append(req)

    for key, req in latest_by_key.items():
        if key not in live_keys and req.status == ReworkRequestStatus.pending.value:
            req.status = ReworkRequestStatus.cancelled.value
            db.add(req)
    db.flush()
    return created


# ---------- read-side decoration --------------------------------------------

def status_by_request_id(
    db: Session, request_ids: set[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Current status of each request - the one source of a row's state."""
    if not request_ids:
        return {}
    return dict(
        db.execute(
            select(ReworkApprovalRequest.id, ReworkApprovalRequest.status).where(
                ReworkApprovalRequest.id.in_(request_ids)
            )
        ).all()
    )


# ---------- notification (after commit, never raises) -----------------------

def _pm_user_ids(db: Session, employee: Employee, project_id: uuid.UUID) -> list[uuid.UUID]:
    """Reporting PM first; the project's assigned PMs only when there is none.
    The requester is never notified about their own request."""
    if employee.reporting_pm_id is not None:
        ids = [employee.reporting_pm_id]
    else:
        ids = list(
            db.execute(
                select(ProjectManager.user_id).where(ProjectManager.project_id == project_id)
            ).scalars()
        )
    return [i for i in ids if i is not None and i != employee.user_id]


def notify_new_requests(db: Session, requests: list[ReworkApprovalRequest]) -> None:
    """Bell + email to the PM for each newly raised request. Never raises."""
    from app.modules.rework_approvals.email import send_request_email

    for req in requests:
        try:
            employee = db.get(Employee, req.employee_id)
            if employee is None:
                continue
            pm_ids = _pm_user_ids(db, employee, req.project_id)
            if not pm_ids:
                logger.info("rework.notify_skipped reason=no_pm request=%s", req.id)
                continue
            from app.modules.notifications.service import create_notification

            for uid in pm_ids:
                create_notification(
                    db,
                    user_id=uid,
                    type_="rework_approval_requested",
                    title=f"Rework approval requested by {employee.full_name}",
                    message=(
                        f"{employee.full_name} submitted '{req.sub_activity_name}' "
                        f"({DAY_PART_LABEL.get(req.day_part, req.day_part)}) on "
                        f"{req.report_date:%d %b %Y} for your approval."
                    ),
                    entity_type="rework_approval_request",
                    entity_id=req.id,
                    target_url=detail_path(req.id),
                )
            db.commit()
            send_request_email(db, employee, req, pm_ids)
        except Exception:  # noqa: BLE001 - the submit already committed
            db.rollback()
            logger.exception("rework.notify_failed request=%s", req.id)
