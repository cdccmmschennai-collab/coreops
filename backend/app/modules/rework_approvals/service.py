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
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import ProjectManager
from app.modules.rework_approvals.models import ReworkApprovalRequest, ReworkRequestStatus
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError
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


# The Weekly Activity Report's REWORK STATUS column (preview + Excel). A
# cancelled cycle is housekeeping, so it maps to nothing (blank cell).
EXPORT_STATUS_LABEL = {
    ReworkRequestStatus.pending.value: "IN REVIEW",
    ReworkRequestStatus.approved.value: "APPROVED",
    ReworkRequestStatus.rejected.value: "REJECTED",
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


# ======================================================================
# Phase 3 - review: listing, detail, approve / reject
# ======================================================================
#
# AUTHORITY: any project_manager may decide any request (the existing
# PM-reviews-everything rule the user confirmed), except their OWN. Enforced
# here, never only in the UI. An email link grants nothing: every endpoint
# requires an authenticated session.
#
# CONCURRENCY: a decision locks the request row (SELECT ... FOR UPDATE) and
# re-checks status == pending under the lock, so two PMs deciding at once
# produce exactly one decision; the loser gets a clean 422.

_LISTED_STATUSES = (
    ReworkRequestStatus.pending.value,
    ReworkRequestStatus.approved.value,
    ReworkRequestStatus.rejected.value,
)


def _is_pm(actor: User) -> bool:
    return actor.role == UserRole.project_manager


def _require_pm(actor: User) -> None:
    if not _is_pm(actor):
        raise AppError("forbidden", "Only project managers can review rework requests.", 403)


def _fetch(db: Session, request_id: uuid.UUID) -> ReworkApprovalRequest:
    req = db.get(ReworkApprovalRequest, request_id)
    if req is None:
        raise AppError("not_found", "Rework request not found.", 404)
    return req


def _user_display_names(db: Session, user_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not user_ids:
        return {}
    names: dict[uuid.UUID, str] = {}
    for emp in db.execute(
        select(Employee).where(Employee.user_id.in_(user_ids), Employee.deleted_at.is_(None))
    ).scalars():
        names.setdefault(emp.user_id, emp.full_name)
    for uid, email in db.execute(select(User.id, User.email).where(User.id.in_(user_ids))).all():
        names.setdefault(uid, email)
    return names


def _serialize(
    db: Session, actor: User, rows: list[ReworkApprovalRequest]
) -> list[dict]:
    if not rows:
        return []
    employees = {
        e.id: e
        for e in db.execute(
            select(Employee).where(Employee.id.in_({r.employee_id for r in rows}))
        ).scalars()
    }
    user_ids = {r.requested_by for r in rows if r.requested_by} | {
        r.reviewer_id for r in rows if r.reviewer_id
    }
    names = _user_display_names(db, user_ids)
    me = _current_employee(db, actor)
    out = []
    for r in rows:
        emp = employees.get(r.employee_id)
        own = me is not None and r.employee_id == me.id
        out.append({
            "id": r.id,
            "report_id": r.report_id,
            "employee_id": r.employee_id,
            "employee_code": (emp.employee_code if emp else "") or "",
            "employee_name": emp.full_name if emp else "",
            "project_id": r.project_id,
            "project_code": r.project_code,
            "project_name": r.project_name,
            "activity_id": r.activity_id,
            "activity_name": r.activity_name,
            "sub_activity_id": r.sub_activity_id,
            "sub_activity_name": r.sub_activity_name,
            "report_date": r.report_date,
            "day_part": r.day_part,
            "employee_remarks": r.employee_remarks,
            "status": r.status,
            "cycle_no": r.cycle_no,
            "requested_at": r.requested_at,
            "requested_by_name": names.get(r.requested_by) if r.requested_by else None,
            "reviewer_name": names.get(r.reviewer_id) if r.reviewer_id else None,
            "review_remarks": r.review_remarks,
            "decided_at": r.decided_at,
            "can_review": _is_pm(actor)
            and not own
            and r.status == ReworkRequestStatus.pending.value,
        })
    return out


def _filtered(
    stmt,
    *,
    project_id: uuid.UUID | None,
    employee_id: uuid.UUID | None,
    report_date: date | None,
    sub_activity_id: uuid.UUID | None,
):
    if project_id is not None:
        stmt = stmt.where(ReworkApprovalRequest.project_id == project_id)
    if employee_id is not None:
        stmt = stmt.where(ReworkApprovalRequest.employee_id == employee_id)
    if report_date is not None:
        stmt = stmt.where(ReworkApprovalRequest.report_date == report_date)
    if sub_activity_id is not None:
        stmt = stmt.where(ReworkApprovalRequest.sub_activity_id == sub_activity_id)
    return stmt


def list_requests(
    db: Session,
    actor: User,
    *,
    status: str | None,
    project_id: uuid.UUID | None,
    employee_id: uuid.UUID | None,
    report_date: date | None,
    sub_activity_id: uuid.UUID | None,
    limit: int,
    offset: int,
) -> dict:
    """PM listing. Filters combine (AND). The summary counts honour every
    filter except status, so the three cards always add up to the rows the
    other filters select. Cancelled cycles are housekeeping, never listed."""
    _require_pm(actor)
    filters = dict(
        project_id=project_id, employee_id=employee_id,
        report_date=report_date, sub_activity_id=sub_activity_id,
    )
    base = _filtered(
        select(ReworkApprovalRequest).where(
            ReworkApprovalRequest.status.in_(_LISTED_STATUSES)
        ),
        **filters,
    )
    counts = {s: 0 for s in _LISTED_STATUSES}
    for st, n in db.execute(
        _filtered(
            select(ReworkApprovalRequest.status, func.count())
            .where(ReworkApprovalRequest.status.in_(_LISTED_STATUSES))
            .group_by(ReworkApprovalRequest.status),
            **filters,
        )
    ).all():
        counts[st] = n
    stmt = base
    if status is not None:
        stmt = stmt.where(ReworkApprovalRequest.status == status)
    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = list(
        db.execute(
            stmt.order_by(
                # Pending first, then newest.
                (ReworkApprovalRequest.status != ReworkRequestStatus.pending.value),
                ReworkApprovalRequest.requested_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        ).scalars()
    )
    return {
        "items": _serialize(db, actor, rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "counts": counts,
    }


def pending_count(db: Session, actor: User) -> int:
    """Pending requests this PM can act on (their own excluded)."""
    _require_pm(actor)
    stmt = select(func.count()).select_from(ReworkApprovalRequest).where(
        ReworkApprovalRequest.status == ReworkRequestStatus.pending.value
    )
    me = _current_employee(db, actor)
    if me is not None:
        stmt = stmt.where(ReworkApprovalRequest.employee_id != me.id)
    return db.execute(stmt).scalar_one()


def filter_options(db: Session, actor: User) -> dict:
    """Dropdown sources built from the requests themselves, so every option
    selects at least one row."""
    _require_pm(actor)
    listed = ReworkApprovalRequest.status.in_(_LISTED_STATUSES)
    projects = db.execute(
        select(
            ReworkApprovalRequest.project_id,
            func.max(ReworkApprovalRequest.project_code),
            func.max(ReworkApprovalRequest.project_name),
        ).where(listed).group_by(ReworkApprovalRequest.project_id)
    ).all()
    employees = db.execute(
        select(Employee).where(
            Employee.id.in_(select(ReworkApprovalRequest.employee_id).where(listed))
        )
    ).scalars().all()
    activities = db.execute(
        select(
            ReworkApprovalRequest.sub_activity_id,
            func.max(ReworkApprovalRequest.activity_name),
            func.max(ReworkApprovalRequest.sub_activity_name),
        ).where(listed).group_by(ReworkApprovalRequest.sub_activity_id)
    ).all()

    def _join(*parts):
        return " - ".join(p for p in parts if p)

    return {
        "projects": sorted(
            ({"value": pid, "label": _join(code, name) or str(pid)} for pid, code, name in projects),
            key=lambda o: o["label"].lower(),
        ),
        "employees": sorted(
            (
                {"value": e.id, "label": _join(e.employee_code, e.full_name)}
                for e in employees
            ),
            key=lambda o: o["label"].lower(),
        ),
        "activities": sorted(
            ({"value": sid, "label": _join(act, sub)} for sid, act, sub in activities),
            key=lambda o: o["label"].lower(),
        ),
    }


def _history(db: Session, req: ReworkApprovalRequest) -> list[ReworkApprovalRequest]:
    """Every cycle of the same report row, oldest first."""
    if req.report_id is None:
        chain = [req]
        prev = req.previous_request_id
        while prev is not None:
            p = db.get(ReworkApprovalRequest, prev)
            if p is None:
                break
            chain.insert(0, p)
            prev = p.previous_request_id
        return chain
    return list(
        db.execute(
            select(ReworkApprovalRequest)
            .where(
                ReworkApprovalRequest.report_id == req.report_id,
                ReworkApprovalRequest.day_part == req.day_part,
                ReworkApprovalRequest.sub_activity_id == req.sub_activity_id,
            )
            .order_by(ReworkApprovalRequest.cycle_no, ReworkApprovalRequest.requested_at)
        ).scalars()
    )


def get_request(db: Session, actor: User, request_id: uuid.UUID) -> dict:
    """Detail for the PM, or for the employee who owns the request."""
    req = _fetch(db, request_id)
    if not _is_pm(actor):
        me = _current_employee(db, actor)
        if me is None or me.id != req.employee_id:
            raise AppError("forbidden", "You cannot view this rework request.", 403)
    [out] = _serialize(db, actor, [req])
    out["history"] = _serialize(db, actor, _history(db, req))

    report = db.get(DailyWorkReport, req.report_id) if req.report_id else None
    out["report_status"] = report.status.value if report is not None else None
    activities = []
    if report is not None:
        part_by_period = dict(
            db.execute(
                select(WorkReportPeriod.id, WorkReportPeriod.day_part).where(
                    WorkReportPeriod.report_id == report.id
                )
            ).all()
        )
        rows = list(
            db.execute(
                select(WorkReportTask)
                .where(WorkReportTask.report_id == report.id)
                .order_by(WorkReportTask.created_at)
            ).scalars()
        )
        statuses = status_by_request_id(
            db, {r.rework_request_id for r in rows if r.rework_request_id}
        )
        for r in rows:
            activities.append({
                "activity_name": r.activity_name,
                "sub_activity_name": r.sub_activity_name,
                "project_code": r.project_code,
                "day_part": part_by_period.get(r.period_id) if r.period_id else None,
                "description": r.description,
                "rework_approval_status": statuses.get(r.rework_request_id)
                if r.rework_request_id
                else None,
            })
    out["report_activities"] = activities
    if report is not None and report.status.value != "submitted":
        # The employee is editing the report; nothing to decide until resubmit.
        out["can_review"] = False
    return out


def _decide(
    db: Session,
    actor: User,
    request_id: uuid.UUID,
    *,
    approve: bool,
    remarks: str | None,
) -> ReworkApprovalRequest:
    _require_pm(actor)
    if not approve and not remarks:
        raise AppError("validation_error", "Rejection remarks are required.", 422)
    req = db.execute(
        select(ReworkApprovalRequest)
        .where(ReworkApprovalRequest.id == request_id)
        .with_for_update()
    ).scalar_one_or_none()
    if req is None:
        raise AppError("not_found", "Rework request not found.", 404)
    me = _current_employee(db, actor)
    if me is not None and req.employee_id == me.id:
        raise AppError("forbidden", "You can't review your own rework request.", 403)
    if req.status != ReworkRequestStatus.pending.value:
        raise AppError("validation_error", "This request has already been decided.", 422)
    report = db.get(DailyWorkReport, req.report_id) if req.report_id else None
    if report is None or report.status.value != "submitted":
        raise AppError(
            "validation_error",
            "The employee is editing this report. Decide it after they resubmit.",
            422,
        )
    req.status = (
        ReworkRequestStatus.approved.value if approve else ReworkRequestStatus.rejected.value
    )
    req.reviewer_id = actor.id
    req.review_remarks = remarks
    req.decided_at = datetime.now(timezone.utc)
    db.add(req)
    from app.modules.audit.service import record_audit

    record_audit(
        db,
        action="rework_request.approved" if approve else "rework_request.rejected",
        actor=actor,
        entity_type="rework_approval_request",
        entity_id=req.id,
        details={"sub_activity": req.sub_activity_name, "report_date": str(req.report_date)},
    )
    db.commit()
    db.refresh(req)
    _notify_decision(db, actor, req)
    return req


def approve_request(db: Session, actor: User, request_id: uuid.UUID, remarks: str | None) -> dict:
    req = _decide(db, actor, request_id, approve=True, remarks=remarks)
    return get_request(db, actor, req.id)


def reject_request(db: Session, actor: User, request_id: uuid.UUID, remarks: str | None) -> dict:
    req = _decide(db, actor, request_id, approve=False, remarks=remarks)
    return get_request(db, actor, req.id)


def _notify_decision(db: Session, actor: User, req: ReworkApprovalRequest) -> None:
    """Bell + email to the employee. Runs after the commit; never raises."""
    from app.modules.rework_approvals.email import send_decision_email

    try:
        employee = db.get(Employee, req.employee_id)
        if employee is None:
            return
        approved = req.status == ReworkRequestStatus.approved.value
        target = f"/work-reports/{req.report_id}" if req.report_id else detail_path(req.id)
        if employee.user_id is not None:
            from app.modules.notifications.service import create_notification

            create_notification(
                db,
                user_id=employee.user_id,
                type_="rework_approval_approved" if approved else "rework_approval_rejected",
                title="Rework activity approved" if approved else "Rework activity rejected",
                message=(
                    f"'{req.sub_activity_name}' on {req.report_date:%d %b %Y} was approved."
                    if approved
                    else f"'{req.sub_activity_name}' on {req.report_date:%d %b %Y} was rejected: "
                    f"{req.review_remarks}. Correct it and resubmit."
                ),
                entity_type="rework_approval_request",
                entity_id=req.id,
                target_url=target,
            )
            db.commit()
        reviewer = _user_display_names(db, {actor.id}).get(actor.id)
        send_decision_email(employee, req, reviewer_name=reviewer, report_path=target)
    except Exception:  # noqa: BLE001 - the decision already committed
        db.rollback()
        logger.exception("rework.decision_notify_failed request=%s", req.id)