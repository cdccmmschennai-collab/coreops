"""ActivityRequest service.

Employees create a request (one click on the work-report form); the project's
PM approves or rejects it from the Activity Requests page. Nothing here touches
work reports, activities, or benchmarks — it is purely a request + notify flow.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster
from app.modules.activity_requests.models import ActivityRequest, ActivityRequestStatus
from app.modules.activity_requests.schemas import ActivityRequestCreate
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import Project, ProjectManager
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    NO_ACTIVITY_DAY_STATUSES,
    DailyWorkReport,
    DayPart,
    ReportMode,
    WorkReportPeriod,
    WorkReportTask,
)
from app.shared.errors import AppError


# ── helpers ──────────────────────────────────────────────────────────────────

def _require_pm(actor: User) -> None:
    if actor.role != UserRole.project_manager:
        raise AppError(
            "forbidden", "Only project managers can manage activity requests.", 403
        )


def _fetch_request(db: Session, request_id: uuid.UUID) -> ActivityRequest:
    req = db.get(ActivityRequest, request_id)
    if req is None:
        raise AppError("not_found", "Activity request not found.", 404)
    return req


def _has_pending_request(
    db: Session, employee_id: uuid.UUID, report_id: uuid.UUID
) -> bool:
    """Whether the employee already has a PENDING request for this report — the
    same predicate the partial unique index enforces at the database level."""
    return (
        db.execute(
            select(ActivityRequest.id).where(
                ActivityRequest.report_id == report_id,
                ActivityRequest.employee_id == employee_id,
                ActivityRequest.status == ActivityRequestStatus.pending.value,
            )
        ).first()
        is not None
    )


def _pm_user_ids(
    db: Session, project_id: uuid.UUID, employee: Employee
) -> list[uuid.UUID]:
    """Notification target user ids for an activity request, in fallback order:
    the employee's **reporting PM**, else the project's assigned PMs
    (``project_managers``, deprecated in place until Phase 6). Each step is used
    only when the previous one is absent.

    The project **Head** is deliberately NOT notified: reviewing an activity
    request (approve/reject) is PM-only (see _ensure_pm), and the PM already sees
    pending requests on the home-page activity-request bar. Notifying the Head —
    who has no way to act on it — was noise, so it routes straight to the PM."""
    # 1. The employee's reporting PM (a user id).
    if employee.reporting_pm_id is not None:
        return [employee.reporting_pm_id]
    # 2. The project's assigned PMs.
    ids = db.execute(
        select(ProjectManager.user_id).where(
            ProjectManager.project_id == project_id
        )
    ).scalars().all()
    return [i for i in ids if i is not None]


def _attach_names(db: Session, requests: list[ActivityRequest]) -> None:
    if not requests:
        return

    emp_ids = {r.employee_id for r in requests}
    project_ids = {r.project_id for r in requests}
    am_ids = {r.sub_activity_id for r in requests}
    am_ids |= {r.activity_id for r in requests if r.activity_id}

    employees = {
        e.id: e
        for e in db.execute(select(Employee).where(Employee.id.in_(emp_ids)))
        .scalars().all()
    }
    projects = {
        p.id: p
        for p in db.execute(select(Project).where(Project.id.in_(project_ids)))
        .scalars().all()
    }
    activities = {
        a.id: a
        for a in db.execute(select(ActivityMaster).where(ActivityMaster.id.in_(am_ids)))
        .scalars().all()
    } if am_ids else {}

    # The requested period's day part ("first_half"/"second_half"/"full_day")
    # so the PM view can tag which half a split-day request targets.
    period_ids = {r.period_id for r in requests if r.period_id}
    day_part_by_period: dict[uuid.UUID, str] = {}
    if period_ids:
        day_part_by_period = dict(db.execute(
            select(WorkReportPeriod.id, WorkReportPeriod.day_part).where(
                WorkReportPeriod.id.in_(period_ids)
            )
        ).all())

    # The employee's current (first) activity in each request's report, so the
    # PM can compare "already logged" vs "requested". Take the earliest task row.
    report_ids = {r.report_id for r in requests if r.report_id}
    first_task_by_report: dict[uuid.UUID, WorkReportTask] = {}
    if report_ids:
        rows = (
            db.execute(
                select(WorkReportTask)
                .where(WorkReportTask.report_id.in_(report_ids))
                .order_by(WorkReportTask.report_id, WorkReportTask.created_at)
            )
            .scalars()
            .all()
        )
        for t in rows:
            first_task_by_report.setdefault(t.report_id, t)

    for r in requests:
        emp = employees.get(r.employee_id)
        proj = projects.get(r.project_id)
        sub = activities.get(r.sub_activity_id)
        act = activities.get(r.activity_id) if r.activity_id else None
        r.employee_name = emp.full_name if emp else ""  # type: ignore[attr-defined]
        r.project_name = proj.name if proj else ""  # type: ignore[attr-defined]
        r.project_code = proj.code if proj else ""  # type: ignore[attr-defined]
        r.activity_name = act.name if act else None  # type: ignore[attr-defined]
        r.sub_activity_name = sub.name if sub else ""  # type: ignore[attr-defined]
        r.task_title = None  # type: ignore[attr-defined]  # Task module removed; kept null for API back-compat
        r.day_part = (  # type: ignore[attr-defined]
            day_part_by_period.get(r.period_id) if r.period_id else None
        )

        current = first_task_by_report.get(r.report_id) if r.report_id else None
        r.current_project_name = current.project_name if current else None  # type: ignore[attr-defined]
        r.current_project_code = current.project_code if current else None  # type: ignore[attr-defined]
        r.current_activity_name = current.activity_name if current else None  # type: ignore[attr-defined]
        r.current_sub_activity_name = current.sub_activity_name if current else None  # type: ignore[attr-defined]


def _notify(
    db: Session,
    *,
    user_ids: list[uuid.UUID],
    type_: str,
    title: str,
    message: str,
    request_id: uuid.UUID,
    target_url: str | None,
) -> None:
    """Best-effort fan-out; a notification failure must not roll back the
    request change the caller already committed."""
    if not user_ids:
        return
    try:
        from app.modules.notifications.service import create_notification

        for uid in user_ids:
            create_notification(
                db,
                user_id=uid,
                type_=type_,
                title=title,
                message=message,
                entity_type="activity_request",
                entity_id=request_id,
                target_url=target_url,
            )
        db.commit()
    except Exception:
        db.rollback()


# ── public API ────────────────────────────────────────────────────────────────

def create_request(
    db: Session, actor: User, data: ActivityRequestCreate
) -> ActivityRequest:
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can request activities.", 403)

    project = db.get(Project, data.project_id)
    if project is None or project.deleted_at is not None:
        raise AppError("not_found", "Project not found.", 404)

    report = db.get(DailyWorkReport, data.report_id)
    if report is None:
        raise AppError("not_found", "Work report not found.", 404)
    if report.employee_id != employee.id:
        raise AppError(
            "forbidden", "You can only request activities on your own report.", 403
        )
    # One pending request per employee/report — mirrors the form's "no further
    # activities while a request is pending" rule and guards against duplicate
    # clicks. This pre-check gives a clean message in the common case; the
    # partial unique index activity_requests_one_pending_per_report_uq is the
    # authoritative guard against a concurrent/duplicate insert (handled below).
    if _has_pending_request(db, employee.id, data.report_id):
        raise AppError(
            "validation_error",
            "A request for this report is already pending approval.",
            422,
        )

    # Additional-activity requests are a FULL-DAY workflow. A split-day half
    # holds exactly one activity by rule, so there is nothing a request could
    # legitimately add — reject at the source rather than letting a request sit
    # pending forever and fail at approval.
    if report.report_mode == ReportMode.split_day.value:
        raise AppError(
            "validation_error",
            "Additional activity requests are not allowed for Split-Day reports.",
            422,
        )

    # Full-day reports may still tag a specific reporting period. Must be one of
    # THIS report's periods and a working one — a leave/off period never takes
    # project activities.
    if data.period_id is not None:
        period = db.get(WorkReportPeriod, data.period_id)
        if period is None or period.report_id != report.id:
            raise AppError(
                "validation_error", "The selected period does not belong to this report.", 422
            )
        if period.period_status is None or period.period_status in NO_ACTIVITY_DAY_STATUSES:
            raise AppError(
                "validation_error", "Activities cannot be added to a non-working period.", 422
            )

    req = ActivityRequest(
        employee_id=employee.id,
        report_id=data.report_id,
        period_id=data.period_id,
        project_id=data.project_id,
        activity_id=data.activity_id,
        sub_activity_id=data.sub_activity_id,
        tags_count=data.tags_count,
        docs_count=data.docs_count,
        bom_count=data.bom_count,
        spares_count=data.spares_count,
        pages_count=data.pages_count,
        records_count=data.records_count,
        status=ActivityRequestStatus.pending.value,
    )
    db.add(req)
    try:
        db.commit()
    except IntegrityError:
        # Lost the race to a concurrent/duplicate create: the unique index
        # rejected the second pending request. Surface it as the same business
        # validation response the pre-check returns, never a 500.
        db.rollback()
        raise AppError(
            "validation_error",
            "A request for this report is already pending approval.",
            422,
        )
    db.refresh(req)

    _attach_names(db, [req])
    _notify(
        db,
        user_ids=_pm_user_ids(db, data.project_id, employee),
        type_="activity_request_created",
        title="New activity request",
        message=(
            f"{req.employee_name} requested activity "  # type: ignore[attr-defined]
            f"'{req.sub_activity_name}' on {req.project_code}."  # type: ignore[attr-defined]
        ),
        request_id=req.id,
        target_url="/activity-requests",
    )
    return req


def list_requests(
    db: Session, actor: User, status: ActivityRequestStatus | None = None
) -> list[ActivityRequest]:
    _require_pm(actor)
    stmt = select(ActivityRequest)
    if status is not None:
        stmt = stmt.where(ActivityRequest.status == status.value)
    rows = list(
        db.execute(stmt.order_by(ActivityRequest.requested_at.desc())).scalars().all()
    )
    _attach_names(db, rows)
    return rows


def list_my_requests(
    db: Session, actor: User, report_id: uuid.UUID
) -> list[ActivityRequest]:
    """Employee — their own requests for one report. Only pending/rejected are
    relevant to the form (approved requests are already normal activity rows)."""
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can view their requests.", 403)
    rows = list(
        db.execute(
            select(ActivityRequest)
            .where(
                ActivityRequest.report_id == report_id,
                ActivityRequest.employee_id == employee.id,
                ActivityRequest.status.in_(
                    [
                        ActivityRequestStatus.pending.value,
                        ActivityRequestStatus.rejected.value,
                    ]
                ),
            )
            .order_by(ActivityRequest.requested_at.desc())
        ).scalars().all()
    )
    _attach_names(db, rows)
    return rows


def delete_request(db: Session, actor: User, request_id: uuid.UUID) -> None:
    """Employee — dismiss/cancel their own request. Allowed while pending or
    rejected (an approved request has already become an activity row)."""
    employee = _current_employee(db, actor)
    if employee is None:
        raise AppError("forbidden", "Only employees can cancel requests.", 403)
    req = _fetch_request(db, request_id)
    if req.employee_id != employee.id:
        raise AppError("forbidden", "You can only cancel your own requests.", 403)
    if req.status == ActivityRequestStatus.approved.value:
        raise AppError(
            "validation_error", "An approved request cannot be cancelled.", 422
        )
    db.delete(req)
    db.commit()


def pending_count(db: Session, actor: User) -> int:
    _require_pm(actor)
    from sqlalchemy import func

    return db.execute(
        select(func.count())
        .select_from(ActivityRequest)
        .where(ActivityRequest.status == ActivityRequestStatus.pending.value)
    ).scalar_one()


def _decide(
    db: Session,
    actor: User,
    request_id: uuid.UUID,
    new_status: ActivityRequestStatus,
) -> ActivityRequest:
    _require_pm(actor)
    req = _fetch_request(db, request_id)
    if req.status != ActivityRequestStatus.pending.value:
        raise AppError(
            "validation_error", "This request has already been decided.", 422
        )

    req.status = new_status.value
    req.approved_by = actor.id
    req.approved_at = datetime.now(timezone.utc)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])

    employee = db.get(Employee, req.employee_id)
    employee_user_ids = (
        [employee.user_id] if employee and employee.user_id else []
    )
    decided = "approved" if new_status == ActivityRequestStatus.approved else "rejected"
    _notify(
        db,
        user_ids=employee_user_ids,
        type_=f"activity_request_{decided}",
        title=f"Activity request {decided}",
        message=(
            f"Your request for activity '{req.sub_activity_name}' "  # type: ignore[attr-defined]
            f"on {req.project_code} was {decided}."  # type: ignore[attr-defined]
        ),
        request_id=req.id,
        target_url=f"/work-reports/{req.report_id}" if req.report_id else None,
    )
    return req


def _create_task_from_request(
    db: Session, req: ActivityRequest, report: DailyWorkReport
) -> None:
    """Turn an approved request into a normal work-report activity row, reusing
    the work-report service's own validation + snapshot conventions so the row
    is indistinguishable from one the employee added directly."""
    # Lazy import avoids a module-load cycle (work_reports.service imports many
    # modules); these helpers freeze project/activity/plant snapshots and derive
    # TASK_BASED dates exactly as the normal add path does.
    from app.modules.work_reports.service import _task_based_dates, _validate_tasks

    periods = db.execute(
        select(WorkReportPeriod)
        .where(WorkReportPeriod.report_id == report.id)
        .order_by(WorkReportPeriod.created_at)
    ).scalars().all()

    # Split Day allows exactly one activity per half and has no additional-
    # activity workflow, so an approval can never land a row in one. This
    # covers a legacy request created before that rule, and a request whose
    # report was converted to split day afterwards — both are refused here
    # rather than falling back to the first working period, which would have
    # silently produced a forbidden second row in First Half.
    if report.report_mode == ReportMode.split_day.value or any(
        p.day_part in (DayPart.first_half.value, DayPart.second_half.value)
        for p in periods
    ):
        raise AppError(
            "validation_error",
            "Additional activity requests cannot be approved for Split-Day "
            "reports — each half allows exactly one activity.",
            422,
        )

    # Which period the approved row lands in: the request's own period when it
    # is still valid, else the report's only working period, else its only
    # period. None only for a pre-period report — the row then stays unlinked
    # like its siblings.
    target_period_id = None
    if req.period_id is not None and any(p.id == req.period_id for p in periods):
        target_period_id = req.period_id
    else:
        working = [
            p for p in periods
            if p.period_status is not None
            and p.period_status not in NO_ACTIVITY_DAY_STATUSES
        ]
        if working:
            target_period_id = working[0].id
        elif periods:
            target_period_id = periods[0].id

    row = SimpleNamespace(
        project_id=req.project_id,
        description="",
        minutes_spent=None,
        task_minutes_spent=None,
        activity_type=None,
        tags_count=req.tags_count,
        docs_count=req.docs_count,
        bom_count=req.bom_count,
        spares_count=req.spares_count,
        pages_count=req.pages_count,
        records_count=req.records_count,
        sub_activity_id=req.sub_activity_id,
        # The approved row starts OPEN regardless of the requested quantity: a
        # workload hint is not progress, and completion is only ever the
        # employee's explicit choice on their own report.
        is_completed=False,
        maintenance_plant_id=None,
    )
    # Validates the project is active and the employee is still a member; raises
    # AppError otherwise so approval fails cleanly instead of writing a bad row.
    _total, snapshots = _validate_tasks(db, req.employee_id, [row])
    snap = snapshots[0]
    started_date, due_date = _task_based_dates(report.report_date, snap)
    db.add(
        WorkReportTask(
            report_id=report.id,
            period_id=target_period_id,
            project_id=row.project_id,
            description=row.description,
            minutes_spent=None,
            task_minutes_spent=None,
            activity_type=snap["activity_type"],
            tags_count=row.tags_count,
            docs_count=row.docs_count,
            bom_count=row.bom_count,
            spares_count=row.spares_count,
            pages_count=row.pages_count,
            records_count=row.records_count,
            sub_activity_id=row.sub_activity_id,
            sub_activity_name=snap["sub_activity_name"],
            activity_name=snap["activity_name"],
            started_date=started_date,
            due_date=due_date,
            is_completed=False,
            completed_date=None,
            maintenance_plant_id=None,
            maintenance_plant_code=snap["maintenance_plant_code"],
            maintenance_plant_description=snap["maintenance_plant_description"],
            planning_plant_code=snap["planning_plant_code"],
            planning_plant_description=snap["planning_plant_description"],
            project_name=snap["project_name"],
            project_code=snap["project_code"],
            project_job_code_code=snap["project_job_code_code"],
        )
    )


def approve_request(
    db: Session, actor: User, request_id: uuid.UUID
) -> ActivityRequest:
    """PM approves: the requested activity becomes a real row in the report, and
    the request is marked approved — both in one transaction so a validation
    failure never leaves an approved request without its row."""
    _require_pm(actor)
    req = _fetch_request(db, request_id)
    if req.status != ActivityRequestStatus.pending.value:
        raise AppError(
            "validation_error", "This request has already been decided.", 422
        )
    report = db.get(DailyWorkReport, req.report_id) if req.report_id else None
    if report is None:
        raise AppError(
            "validation_error",
            "The work report for this request no longer exists.",
            422,
        )

    _create_task_from_request(db, req, report)
    req.status = ActivityRequestStatus.approved.value
    req.approved_by = actor.id
    req.approved_at = datetime.now(timezone.utc)
    db.add(req)
    db.commit()
    db.refresh(req)

    _attach_names(db, [req])

    employee = db.get(Employee, req.employee_id)
    employee_user_ids = [employee.user_id] if employee and employee.user_id else []
    _notify(
        db,
        user_ids=employee_user_ids,
        type_="activity_request_approved",
        title="Activity request approved",
        message=(
            f"Your request for activity '{req.sub_activity_name}' "  # type: ignore[attr-defined]
            f"on {req.project_code} was approved."  # type: ignore[attr-defined]
        ),
        request_id=req.id,
        target_url=f"/work-reports/{req.report_id}" if req.report_id else None,
    )
    return req


def reject_request(
    db: Session, actor: User, request_id: uuid.UUID
) -> ActivityRequest:
    return _decide(db, actor, request_id, ActivityRequestStatus.rejected)
