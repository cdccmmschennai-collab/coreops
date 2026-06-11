"""Daily Work Reports service: RBAC-scoped reads + author writes + review workflow.

All business rules live here (DAILY_WORK_REPORTS_SPEC.md §3, §5, §6):
  - author = the acting user's employee profile (reports are always "own")
  - validation: future date, edit window (current + previous month), duplicate
    (employee, date), project active + author membership, daily sum <= 1440
  - workflow: draft -> submitted (final). No approval step; a submitted report
    is locked from further edits.
  - total_minutes is derived (sum of task minutes), never client-supplied

RBAC (this module):
  admin    full access
  manager  own + team (direct reports via manager_id); reads team reports
  employee own reports only
  viewer   read all, no writes
Manager "team" = employees whose manager_id == the manager's employee id.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.job_codes.models import JobCode
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DailyWorkReport,
    WorkReportStatus,
    WorkReportTask,
)
from app.modules.work_reports.schemas import (
    WorkReportCreate,
    WorkReportEditRequest,
    WorkReportReject,
    WorkReportUpdate,
)
from app.shared.errors import AppError

MAX_DAY_MINUTES = 1440


def _push(db: Session, user_id: uuid.UUID, type_: str, title: str, message: str,
          entity_id: uuid.UUID | None = None, target_url: str | None = None) -> None:
    try:
        from app.modules.notifications.service import create_notification
        create_notification(db, user_id=user_id, type_=type_, title=title, message=message,
                            entity_type="daily_work_report", entity_id=entity_id,
                            target_url=target_url)
        db.commit()
    except Exception:
        db.rollback()


def _notify_manager(db: Session, author: Employee, type_: str, title: str,
                    message: str, entity_id: uuid.UUID | None = None,
                    target_url: str | None = None) -> None:
    if author.manager_id is None:
        return
    mgr = db.get(Employee, author.manager_id)
    if mgr is None or mgr.user_id is None:
        return
    _push(db, mgr.user_id, type_, title, message, entity_id, target_url)


def _notify_author(db: Session, report: DailyWorkReport, type_: str, title: str,
                   message: str) -> None:
    author = db.get(Employee, report.employee_id)
    if author is None or author.user_id is None:
        return
    _push(db, author.user_id, type_, title, message, report.id,
          f"/work-reports/{report.id}")


def _notify_reviewers(db: Session, report: DailyWorkReport, author: Employee,
                      type_: str, title: str, message: str) -> None:
    """Notify the report's reviewers: team leads on its projects + the author's
    manager. (Requires report.tasks to be attached.)"""
    url = f"/work-reports/{report.id}"
    project_ids = {t.project_id for t in getattr(report, "tasks", [])}
    if project_ids:
        lead_emp_ids = db.execute(
            select(ProjectMember.employee_id).where(
                ProjectMember.project_id.in_(project_ids),
                ProjectMember.role == ProjectMemberRole.team_lead,
            )
        ).scalars().all()
        for emp_id in set(lead_emp_ids):
            if emp_id == author.id:
                continue
            lead = db.get(Employee, emp_id)
            if lead and lead.user_id:
                _push(db, lead.user_id, type_, title, message, report.id, url)
    _notify_manager(db, author, type_, title, message, report.id, url)


_EDITABLE = {
    WorkReportStatus.draft,
    WorkReportStatus.rejected,
    WorkReportStatus.granted,
}


def _led_project_ids(db: Session, employee_id: uuid.UUID) -> set[uuid.UUID]:
    """Project ids where this employee is a team lead (drives scoped review)."""
    rows = db.execute(
        select(ProjectMember.project_id).where(
            ProjectMember.employee_id == employee_id,
            ProjectMember.role == ProjectMemberRole.team_lead,
        )
    ).scalars().all()
    return set(rows)


def _report_in_projects(
    db: Session, report_id: uuid.UUID, project_ids: set[uuid.UUID]
) -> bool:
    if not project_ids:
        return False
    return db.execute(
        select(WorkReportTask.id).where(
            WorkReportTask.report_id == report_id,
            WorkReportTask.project_id.in_(project_ids),
        ).limit(1)
    ).scalar_one_or_none() is not None


def _decorate(
    db: Session, actor: User, reports: list[DailyWorkReport]
) -> list[DailyWorkReport]:
    """Attach tasks and the per-actor `can_review` flag to each report.

    can_review = PM (any report) OR team lead on one of the report's projects
    (but never one's own report — authors request edits, they don't grant them).
    """
    _attach_tasks(db, reports)
    # Resolve author display names server-side so scoped viewers (team leads)
    # don't depend on the RBAC-limited employee list to show who filed a report.
    if reports:
        emp_ids = {r.employee_id for r in reports}
        # full_name is a Python @property, not a column — load the rows and read it.
        emps = db.execute(
            select(Employee).where(Employee.id.in_(emp_ids))
        ).scalars().all()
        names = {e.id: e.full_name for e in emps}
        for r in reports:
            r.employee_name = names.get(r.employee_id)
    if actor.role == UserRole.project_manager:
        for r in reports:
            r.can_review = True
        return reports
    me = _current_employee(db, actor)
    led_ids = _led_project_ids(db, me.id) if me is not None else set()
    for r in reports:
        r.can_review = (
            me is not None
            and r.employee_id != me.id
            and any(t.project_id in led_ids for t in r.tasks)
        )
    return reports


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


def _validate_tasks(
    db: Session, author_id: uuid.UUID, tasks
) -> tuple[int, list[dict]]:
    """Validate project (active) + membership; return (total_minutes, snapshots).

    Each snapshot dict carries the project_name, project_code, and
    project_job_code_code frozen at validation time so they can be written
    directly into the task row for historical accuracy.
    """
    total = 0
    snapshots: list[dict] = []
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
        job_code_code: str | None = None
        if project.job_code_id:
            jc = db.get(JobCode, project.job_code_id)
            job_code_code = jc.code if jc else None
        snapshots.append({
            "project_name": project.name,
            "project_code": project.code,
            "project_job_code_code": job_code_code,
        })
        total += (task.minutes_spent or 0)
    if total > MAX_DAY_MINUTES:
        raise AppError(
            "validation_error", "Total minutes cannot exceed 1440 for a single day.", 422
        )
    return total, snapshots


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


# ---------- reads ----------------------------------------------------------
def _apply_scope(db: Session, actor: User, stmt):
    """Return (stmt, allowed). allowed=False short-circuits to an empty page.

    PM sees all. Everyone else sees their own reports, plus — if they are a team
    lead on any project — every report that includes a task on one of those
    projects (project-scoped read).
    """
    if actor.role == UserRole.project_manager:
        return stmt, True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    led_ids = _led_project_ids(db, me.id)
    if led_ids:
        led_reports = select(WorkReportTask.report_id).where(
            WorkReportTask.project_id.in_(led_ids)
        )
        return stmt.where(
            or_(
                DailyWorkReport.employee_id == me.id,
                DailyWorkReport.id.in_(led_reports),
            )
        ), True
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
    _decorate(db, actor, reports)
    return reports, total


def _assert_can_read(db: Session, actor: User, report: DailyWorkReport) -> None:
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None:
        raise AppError("forbidden", "Not permitted.", 403)
    if report.employee_id == me.id:
        return
    if _report_in_projects(db, report.id, _led_project_ids(db, me.id)):
        return
    raise AppError(
        "forbidden",
        "You can only view your own reports or reports on projects you lead.",
        403,
    )


def _fetch(db: Session, report_id: uuid.UUID) -> DailyWorkReport:
    report = db.get(DailyWorkReport, report_id)
    if report is None:
        raise AppError("not_found", "Work report not found.", 404)
    return report


def get_work_report(db: Session, actor: User, report_id: uuid.UUID) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_can_read(db, actor, report)
    return _decorate(db, actor, [report])[0]


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

    total, snapshots = _validate_tasks(db, me.id, data.tasks)

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
    for task, snap in zip(data.tasks, snapshots):
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
                project_name=snap["project_name"],
                project_code=snap["project_code"],
                project_job_code_code=snap["project_job_code_code"],
            )
        )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise AppError("conflict", "A work report for this date already exists.", 409)
    db.refresh(report)
    return _decorate(db, actor, [report])[0]


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
        total, snapshots = _validate_tasks(db, me.id, data.tasks)
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        for task, snap in zip(data.tasks, snapshots):
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
                    project_name=snap["project_name"],
                    project_code=snap["project_code"],
                    project_job_code_code=snap["project_job_code_code"],
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

    # Editing a reopened report (rejected / granted) returns it to draft and
    # clears the prior review.
    if report.status in (WorkReportStatus.rejected, WorkReportStatus.granted):
        report.status = WorkReportStatus.draft
        report.submitted_at = None
        report.reviewed_by = None
        report.reviewed_at = None
        report.review_note = None
        report.edit_requested_at = None
        report.edit_request_note = None

    report.updated_by = actor.id
    db.add(report)
    db.commit()
    db.refresh(report)
    return _decorate(db, actor, [report])[0]


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
    report.edit_requested_at = None
    report.edit_request_note = None
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
            f"/work-reports/{report.id}",
        )
    return _decorate(db, actor, [report])[0]


# ---------- edit-access workflow -------------------------------------------
def _assert_can_review(db: Session, actor: User, report: DailyWorkReport) -> None:
    """Reviewers = PM (any report) or a team lead on one of the report's
    projects. A user can never review their own report."""
    if actor.role == UserRole.project_manager:
        return
    me = _current_employee(db, actor)
    if me is None or report.employee_id == me.id:
        raise AppError("forbidden", "You are not permitted to review this report.", 403)
    if _report_in_projects(db, report.id, _led_project_ids(db, me.id)):
        return
    raise AppError("forbidden", "You are not permitted to review this report.", 403)


def request_edit_work_report(
    db: Session, actor: User, report_id: uuid.UUID, data: WorkReportEditRequest
) -> DailyWorkReport:
    """Author asks a reviewer to reopen a submitted (locked) report for editing,
    with a reason explaining why the edit is needed."""
    report = _fetch(db, report_id)
    author = _assert_author(db, actor, report)
    if report.status != WorkReportStatus.submitted:
        raise AppError(
            "validation_error",
            "Only a submitted report can be requested for editing.",
            422,
        )
    report.edit_requested_at = _now()
    report.edit_request_note = data.note
    db.add(report)
    db.commit()
    db.refresh(report)
    decorated = _decorate(db, actor, [report])[0]
    _notify_reviewers(
        db, decorated, author, "report_edit_requested",
        f"{author.full_name} requested to edit a report",
        f"{author.full_name} asked to edit their work report for "
        f"{report.report_date}. Reason: {data.note}",
    )
    return decorated


def reject_work_report(
    db: Session, actor: User, report_id: uuid.UUID, data: WorkReportReject
) -> DailyWorkReport:
    """Reviewer sends a submitted report back to the author for changes."""
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
    report.edit_requested_at = None
    report.edit_request_note = None
    db.add(report)
    db.commit()
    db.refresh(report)
    _notify_author(
        db, report, "report_rejected",
        "Your work report was sent back",
        f"Your work report for {report.report_date} was sent back for changes."
        + (f" Note: {data.review_note}" if data.review_note else ""),
    )
    return _decorate(db, actor, [report])[0]


def grant_edit_work_report(
    db: Session, actor: User, report_id: uuid.UUID
) -> DailyWorkReport:
    """Reviewer grants an edit request — reopens the report so the author can
    edit and resubmit. Uses the editable 'rejected' state."""
    report = _fetch(db, report_id)
    _assert_can_review(db, actor, report)
    if report.status != WorkReportStatus.submitted:
        raise AppError(
            "validation_error",
            "Only a submitted report can be reopened for editing.",
            422,
        )
    report.status = WorkReportStatus.granted
    report.reviewed_by = actor.id
    report.reviewed_at = _now()
    report.review_note = None
    report.edit_requested_at = None
    report.edit_request_note = None
    db.add(report)
    db.commit()
    db.refresh(report)
    _notify_author(
        db, report, "report_edit_granted",
        "Edit access granted",
        f"You can now edit and resubmit your work report for {report.report_date}.",
    )
    return _decorate(db, actor, [report])[0]


def delete_work_report(db: Session, actor: User, report_id: uuid.UUID) -> None:
    report = _fetch(db, report_id)
    _assert_author(db, actor, report)
    if report.status != WorkReportStatus.draft:
        raise AppError("forbidden", "Only draft reports can be deleted.", 403)
    db.delete(report)
    db.commit()
