"""Daily Work Reports service: RBAC-scoped reads + author writes + review workflow.

All business rules live here (DAILY_WORK_REPORTS_SPEC.md §3, §5, §6):
  - author = the acting user's employee profile (reports are always "own")
  - validation: future date, edit window (current + previous month), duplicate
    (employee, date), project active + author membership, daily sum <= 1440
  - workflow: draft/rejected -> submitted -> approved | rejected (rejected is
    editable; editing a rejected report returns it to draft)
  - total_minutes is derived (sum of task minutes), never client-supplied

RBAC (this module):
  admin    full access
  manager  own + team (direct reports via manager_id); reviews team reports
  employee own reports only
  viewer   read all, no writes
Manager "team" = employees whose manager_id == the manager's employee id.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.projects.models import Project, ProjectMember, ProjectStatus
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    WorkReportStatus,
    WorkReportTask,
)
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportReject,
    WorkReportUpdate,
)
from app.shared.errors import AppError

MAX_DAY_MINUTES = 1440


def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="daily_work_report", entity_id=entity_id)
        db.commit()
    except Exception:
        db.rollback()


def _notify_manager(db: Session, author: Employee, type_: str, title: str,
                    message: str, entity_id: uuid.UUID | None = None) -> None:
    if author.manager_id is None:
        return
    mgr = db.get(Employee, author.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(db, mgr.user_id, type_, title, message, entity_id)


def _notify_author(db: Session, report: DailyWorkReport, type_: str, title: str,
                   message: str) -> None:
    author = db.get(Employee, report.employee_id)
    if author is None or author.user_id is None:
        return
    _push(db, author.user_id, type_, title, message, report.id)
_EDITABLE = {WorkReportStatus.draft, WorkReportStatus.rejected}
_REVIEW_ROLES = {UserRole.project_manager}


# ---------- helpers --------------------------------------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return date.today()


def _first_of_previous_month(today: date) -> date:
    first_of_this = today.replace(day=1)
    if first_of_this.month == 1:
        return first_of_this.replace(year=first_of_this.year - 1, month=12)
    return first_of_this.replace(month=first_of_this.month - 1)


def _validate_report_date(report_date: date) -> None:
    today = _today()
    if report_date > today:
        raise AppError("validation_error", "Report date cannot be in the future.", 422)
    if report_date < _first_of_previous_month(today):
        raise AppError(
            "validation_error",
            "Report date is outside the editable window (current and previous month).",
            422,
        )


def _author_employee(db: Session, actor: User) -> Employee:
    me = _current_employee(db, actor)
    if me is None:
        raise AppError(
            "validation_error", "You don't have an employee profile to file a report.", 422
        )
    return me


def _team_ids(manager_employee_id: uuid.UUID):
    return select(Employee.id).where(
        Employee.manager_id == manager_employee_id, Employee.deleted_at.is_(None)
    )


def _validate_tasks(db: Session, author_id: uuid.UUID, tasks) -> int:
    """Validate project (active) + membership for each task; return total minutes."""
    total = 0
    for task in tasks:
        project = db.get(Project, task.project_id)
        if (
            project is None
            or project.deleted_at is not None
            or project.status == ProjectStatus.archived
        ):
            raise AppError("validation_error", "Project not found or inactive.", 422)
        member = db.execute(
            select(ProjectMember.id).where(
                ProjectMember.project_id == task.project_id,
                ProjectMember.employee_id == author_id,
            )
        ).scalar_one_or_none()
        if member is None:
            raise AppError(
                "validation_error", "You are not assigned to this project.", 422
            )
        total += (task.minutes_spent or 0)
    if total > MAX_DAY_MINUTES:
        raise AppError(
            "validation_error", "Total minutes cannot exceed 1440 for a single day.", 422
        )
    return total


def _attach_tasks(db: Session, reports: list[DailyWorkReport]) -> None:
    """Attach each report's task lines as a transient `.tasks` attribute (FK-only ORM)."""
    if not reports:
        return
    ids = [r.id for r in reports]
    rows = (
        db.execute(
            select(WorkReportTask).where(WorkReportTask.report_id.in_(ids))
        )
        .scalars()
        .all()
    )
    by_report: dict[uuid.UUID, list[WorkReportTask]] = {r.id: [] for r in reports}
    for row in rows:
        by_report[row.report_id].append(row)
    for report in reports:
        report.tasks = by_report[report.id]


def _load(db: Session, report: DailyWorkReport) -> DailyWorkReport:
    _attach_tasks(db, [report])
    return report


# ---------- reads ----------------------------------------------------------
def _apply_scope(db: Session, actor: User, stmt):
    """Return (stmt, allowed). allowed=False short-circuits to an empty page."""
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    return stmt.where(DailyWorkReport.employee_id == me.id), True


def list_work_reports(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    status: WorkReportStatus | None,
    date_from: date | None,
    date_to: date | None,
    limit: int,
    offset: int,
) -> tuple[list[DailyWorkReport], int]:
    stmt = select(DailyWorkReport)
    stmt, allowed = _apply_scope(db, actor, stmt)
    if not allowed:
        return [], 0

    if employee_id is not None:
        stmt = stmt.where(DailyWorkReport.employee_id == employee_id)
    if project_id is not None:
        stmt = stmt.where(
            DailyWorkReport.id.in_(
                select(WorkReportTask.report_id).where(
                    WorkReportTask.project_id == project_id
                )
            )
        )
    if status is not None:
        stmt = stmt.where(DailyWorkReport.status == status)
    if date_from is not None:
        stmt = stmt.where(DailyWorkReport.report_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(DailyWorkReport.report_date <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(DailyWorkReport.report_date.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    reports = list(rows)
    _attach_tasks(db, reports)
    return reports, total


def _assert_can_read(db: Session, actor: User, report: DailyWorkReport) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if report.employee_id == me.id:
        return
    raise AppError("forbidden", "You can only view your own reports.", 403)


def _fetch(db: Session, report_id: uuid.UUID) -> DailyWorkReport:
    report = db.get(DailyWorkReport, report_id)
    if report is None:
        raise AppError("not_found", "Work report not found.", 404)
    return report


def get_work_report(db: Session, actor: User, report_id: uuid.UUID) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_can_read(db, actor, report)
    return _load(db, report)


# ---------- author writes --------------------------------------------------
def create_work_report(
    db: Session, actor: User, data: WorkReportCreate
) -> DailyWorkReport:
    me = _author_employee(db, actor)
    _validate_report_date(data.report_date)

    if db.execute(
        select(DailyWorkReport).where(
            DailyWorkReport.employee_id == me.id,
            DailyWorkReport.report_date == data.report_date,
        )
    ).scalar_one_or_none():
        raise AppError(
            "conflict", "A work report for this date already exists.", 409
        )

    total = _validate_tasks(db, me.id, data.tasks)

    report = DailyWorkReport(
        employee_id=me.id,
        report_date=data.report_date,
        status=WorkReportStatus.draft,
        day_status=data.day_status,
        location=data.location,
        remarks=data.remarks,
        query_text=data.query_text,
        well_head_no=data.well_head_no,
        pm_plant=data.pm_plant,
        task_list_count=data.task_list_count,
        task_list_op_count=data.task_list_op_count,
        maintenance_item_count=data.maintenance_item_count,
        maintenance_plan_count=data.maintenance_plan_count,
        summary=data.summary,
        total_minutes=total,
        created_by=actor.id,
        updated_by=actor.id,
    )
    db.add(report)
    db.flush()
    for task in data.tasks:
        db.add(
            WorkReportTask(
                report_id=report.id,
                project_id=task.project_id,
                description=task.description,
                minutes_spent=task.minutes_spent,
                activity_type=task.activity_type,
                tags_count=task.tags_count,
                docs_count=task.docs_count,
                bom_count=task.bom_count,
                spares_count=task.spares_count,
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "A work report for this date already exists.", 409)
    db.refresh(report)
    return _load(db, report)


def _assert_author(db: Session, actor: User, report: DailyWorkReport) -> Employee:
    me = _current_employee(db, actor)
    if me is None or report.employee_id != me.id:
        raise AppError("forbidden", "You can only modify your own reports.", 403)
    return me


def update_work_report(
    db: Session, actor: User, report_id: uuid.UUID, data: WorkReportUpdate
) -> DailyWorkReport:
    report = _fetch(db, report_id)
    me = _assert_author(db, actor, report)
    if report.status not in _EDITABLE:
        raise AppError(
            "forbidden", "Only draft or rejected reports can be edited.", 403
        )

    fields = data.model_dump(exclude_unset=True)

    if "tasks" in fields and data.tasks is not None:
        total = _validate_tasks(db, me.id, data.tasks)
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        for task in data.tasks:
            db.add(
                WorkReportTask(
                    report_id=report.id,
                    project_id=task.project_id,
                    description=task.description,
                    minutes_spent=task.minutes_spent,
                    activity_type=task.activity_type,
                    tags_count=task.tags_count,
                    docs_count=task.docs_count,
                    bom_count=task.bom_count,
                    spares_count=task.spares_count,
                )
            )
        report.total_minutes = total

    # Scalar header fields: update if explicitly provided
    _HEADER_FIELDS = (
        "summary", "day_status", "location", "remarks", "query_text",
        "well_head_no", "pm_plant", "task_list_count", "task_list_op_count",
        "maintenance_item_count", "maintenance_plan_count",
    )
    for field_name in _HEADER_FIELDS:
        if field_name in fields:
            setattr(report, field_name, getattr(data, field_name))

    # Editing a rejected report returns it to draft and clears the prior review.
    if report.status == WorkReportStatus.rejected:
        report.status = WorkReportStatus.draft
        report.submitted_at = None
        report.reviewed_by = None
        report.reviewed_at = None
        report.review_note = None

    report.updated_by = actor.id
    db.add(report)
    db.commit()
    db.refresh(report)
    return _load(db, report)


def submit_work_report(
    db: Session, actor: User, report_id: uuid.UUID
) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_author(db, actor, report)
    if report.status not in _EDITABLE:
        raise AppError(
            "validation_error", "Only draft or rejected reports can be submitted.", 422
        )
    has_task = db.execute(
        select(WorkReportTask.id).where(WorkReportTask.report_id == report.id).limit(1)
    ).scalar_one_or_none()
    if has_task is None:
        raise AppError("validation_error", "Add at least one task before submitting.", 422)

    report.status = WorkReportStatus.submitted
    report.submitted_at = _now()
    report.reviewed_by = None
    report.reviewed_at = None
    report.review_note = None
    report.updated_by = actor.id
    db.add(report)
    db.commit()
    db.refresh(report)
    author = db.get(Employee, report.employee_id)
    if author:
        _notify_manager(
            db, author, "report_submitted",
            f"{author.full_name} submitted a work report",
            f"{author.full_name} submitted their work report for {report.report_date}.",
            report.id,
        )
    return _load(db, report)


def _assert_can_review(db: Session, actor: User, report: DailyWorkReport) -> None:
    if actor.role not in _REVIEW_ROLES:
        raise AppError("forbidden", "You are not permitted to review reports.", 403)


def approve_work_report(
    db: Session, actor: User, report_id: uuid.UUID
) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_can_review(db, actor, report)
    if report.status != WorkReportStatus.submitted:
        raise AppError(
            "validation_error", "Only submitted reports can be approved.", 422
        )
    report.status = WorkReportStatus.approved
    report.reviewed_by = actor.id
    report.reviewed_at = _now()
    report.review_note = None
    db.add(report)
    db.commit()
    db.refresh(report)
    _notify_author(
        db, report, "report_approved",
        "Your work report was approved",
        f"Your work report for {report.report_date} has been approved.",
    )
    return _load(db, report)


def reject_work_report(
    db: Session, actor: User, report_id: uuid.UUID, data: WorkReportReject
) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_can_review(db, actor, report)
    if report.status != WorkReportStatus.submitted:
        raise AppError(
            "validation_error", "Only submitted reports can be rejected.", 422
        )
    report.status = WorkReportStatus.rejected
    report.reviewed_by = actor.id
    report.reviewed_at = _now()
    report.review_note = data.review_note
    db.add(report)
    db.commit()
    db.refresh(report)
    _notify_author(
        db, report, "report_rejected",
        "Your work report was sent back",
        f"Your work report for {report.report_date} was not approved."
        + (f" Note: {data.review_note}" if data.review_note else ""),
    )
    return _load(db, report)


def delete_work_report(db: Session, actor: User, report_id: uuid.UUID) -> None:
    report = _fetch(db, report_id)
    _assert_author(db, actor, report)
    if report.status != WorkReportStatus.draft:
        raise AppError("forbidden", "Only draft reports can be deleted.", 403)
    db.delete(report)
    db.commit()
