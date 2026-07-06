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
from datetime import date, datetime, timedelta, timezone
from itertools import groupby

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modules.activity_master.models import ActivityMaster, LEVEL_SUB_ACTIVITY
from app.modules.activity_master.service import compute_benchmark, compute_overdue
from app.modules.employees.models import Employee
from app.modules.employees.service import _current_employee
from app.modules.job_codes.models import JobCode
from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectMemberRole,
    ProjectStatus,
)
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    NO_ACTIVITY_DAY_STATUSES,
    DailyWorkReport,
    DayStatus,
    WorkReportStatus,
    WorkReportTask,
)
from app.modules.work_reports.schemas import (
    TaskCompletionUpdate,
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


def _task_based_dates(report_date: date, snap: dict) -> tuple[date | None, date | None]:
    """started_date/due_date for a TASK_BASED row — never client-supplied.
    started_date is always the report's own date (stable across edits, since
    report_date itself never changes). Benchmark activities are daily production
    work, so due_date defaults to the *assigned date*: a 1-day activity
    (benchmark_period_days = 1, the default) is due the same day it's reported,
    never pushed to the next day. A multi-day activity spans forward — due on
    started_date + (benchmark_period_days - 1), so a 2-day activity is due the
    following day, and so on."""
    if not snap["is_task_based"]:
        return None, None
    started = report_date
    due = started + timedelta(days=(snap["benchmark_period_days"] or 1) - 1)
    return started, due


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
        # Optional Activity Master selection: replaces free-text activity_type.
        sub_activity_name: str | None = None
        activity_name: str | None = None
        activity_type = getattr(task, "activity_type", None)
        is_task_based = False
        benchmark_period_days: int | None = None
        if getattr(task, "sub_activity_id", None) is not None:
            sub = db.get(ActivityMaster, task.sub_activity_id)
            if (
                sub is None
                or sub.level != LEVEL_SUB_ACTIVITY
                or not sub.is_active
            ):
                raise AppError(
                    "validation_error", "Selected sub-activity is invalid or inactive.", 422
                )
            parent = db.get(ActivityMaster, sub.parent_id)
            sub_activity_name = sub.name
            activity_name = parent.name if parent else None
            if not activity_type:
                activity_type = (
                    f"{activity_name} / {sub_activity_name}" if activity_name else sub_activity_name
                )
            is_task_based = sub.benchmark_type == "TASK_BASED"
            benchmark_period_days = sub.benchmark_period_days
        # Optional Maintenance Plant selection — independent of the project's
        # own assigned plant; which plant the employee worked at that day.
        maintenance_plant_code: str | None = None
        maintenance_plant_description: str | None = None
        planning_plant_code: str | None = None
        planning_plant_description: str | None = None
        if getattr(task, "maintenance_plant_id", None) is not None:
            mp = db.get(MaintenancePlant, task.maintenance_plant_id)
            if mp is None or not mp.is_active:
                raise AppError(
                    "validation_error", "Selected maintenance plant is invalid or inactive.", 422
                )
            pp = db.get(PlanningPlant, mp.planning_plant_id)
            maintenance_plant_code = mp.code
            maintenance_plant_description = mp.description
            planning_plant_code = pp.code if pp else None
            planning_plant_description = pp.description if pp else None
        snapshots.append({
            "project_name": project.name,
            "project_code": project.code,
            "project_job_code_code": job_code_code,
            "sub_activity_name": sub_activity_name,
            "activity_name": activity_name,
            "activity_type": activity_type,
            "is_task_based": is_task_based,
            "benchmark_period_days": benchmark_period_days,
            "maintenance_plant_code": maintenance_plant_code,
            "maintenance_plant_description": maintenance_plant_description,
            "planning_plant_code": planning_plant_code,
            "planning_plant_description": planning_plant_description,
        })
        total += (task.minutes_spent or 0) + (getattr(task, "task_minutes_spent", None) or 0)
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
    today = _today()
    for row in rows:
        # Transient, computed fresh on every read (never stored) — same
        # pattern as report.can_review below.
        row.is_overdue, row.days_overdue = compute_overdue(row.due_date, row.is_completed, today)
        by_report[row.report_id].append(row)
    for report in reports:
        report.tasks = by_report[report.id]


# ---------- reads ----------------------------------------------------------
_REVIEWABLE = {
    WorkReportStatus.submitted,
    WorkReportStatus.rejected,
    WorkReportStatus.granted,
}


def _apply_scope(db: Session, actor: User, stmt):
    """Return (stmt, allowed). allowed=False short-circuits to an empty page.

    PM sees all non-draft reports (submitted/granted/rejected/approved) — drafts
    are private to the author until filed. This keeps PM dashboards complete:
    a report reopened for edit ('granted') or sent back ('rejected') still
    represents real work and must remain visible.
    TL sees own reports (all statuses) + submitted/rejected/granted reports
    from their led projects, so they can still track a report they sent
    back or granted edit access to, not just the moment it's re-submitted.
    Everyone else sees only their own reports (all statuses).
    """
    if actor.role == UserRole.project_manager:
        return stmt.where(DailyWorkReport.status != WorkReportStatus.draft), True
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
                and_(
                    DailyWorkReport.id.in_(led_reports),
                    DailyWorkReport.status.in_(_REVIEWABLE),
                ),
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


DAY_STATUS_LABELS: dict[str, str] = {
    DayStatus.leave.value: "Leave",
    DayStatus.company_holiday.value: "Company Holiday",
    DayStatus.work_from_home.value: "Work From Home",
    DayStatus.week_off.value: "Week Off",
    DayStatus.work_at_office.value: "Work at Office",
    DayStatus.half_day.value: "Half Day",
    DayStatus.comp_off.value: "Comp-off",
    DayStatus.overtime_compensation.value: "Overtime Hours-Compensation",
    DayStatus.overtime_salary.value: "Overtime Hours-Salary",
    # "P / …" marks a Present day on which the employee took some permission.
    DayStatus.permission_first_half_1hr.value: "P / Permission-First Half 1HR",
    DayStatus.permission_second_half_1hr.value: "P / Permission-Second Half 1HR",
    DayStatus.permission_first_half_2hr.value: "P / Permission-First Half 2HR",
    DayStatus.permission_second_half_2hr.value: "P / Permission-Second Half 2HR",
}


def build_activity_rows(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    sub_activity_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict]:
    """Activity-level rows for the PM Weekly Activity Report (preview + Excel
    export share this one source). One row per work_report_task, RBAC-scoped the
    same way the report list is (`_apply_scope`: PM sees all non-draft). Built
    from detailed task records — never from report summaries — so project code /
    activity / counts / remarks stay accurate."""
    scoped = select(DailyWorkReport.id)
    scoped, allowed = _apply_scope(db, actor, scoped)
    if not allowed:
        return []

    q = (
        select(WorkReportTask, DailyWorkReport, Employee)
        .join(DailyWorkReport, DailyWorkReport.id == WorkReportTask.report_id)
        .join(Employee, Employee.id == DailyWorkReport.employee_id)
        .where(WorkReportTask.report_id.in_(scoped))
    )
    if employee_id is not None:
        q = q.where(DailyWorkReport.employee_id == employee_id)
    if project_id is not None:
        q = q.where(WorkReportTask.project_id == project_id)
    if sub_activity_id is not None:
        q = q.where(WorkReportTask.sub_activity_id == sub_activity_id)
    if activity_id is not None:
        q = q.join(
            ActivityMaster, ActivityMaster.id == WorkReportTask.sub_activity_id
        ).where(ActivityMaster.parent_id == activity_id)
    if date_from is not None:
        q = q.where(DailyWorkReport.report_date >= date_from)
    if date_to is not None:
        q = q.where(DailyWorkReport.report_date <= date_to)
    q = q.order_by(Employee.employee_code, DailyWorkReport.report_date, WorkReportTask.id)

    rows: list[dict] = []
    for task, report, emp in db.execute(q).all():
        rows.append({
            "employee_label": f"{emp.employee_code} - {emp.full_name}",
            "report_date": report.report_date,
            "day_status": (
                DAY_STATUS_LABELS.get(report.day_status.value, report.day_status.value)
                if report.day_status
                else None
            ),
            "project_code": task.project_code,
            "activity_type": task.activity_name,
            "sub_activity_type": task.sub_activity_name,
            "tags": task.tags_count,
            "docs": task.docs_count,
            "bom": task.bom_count,
            "spares": task.spares_count,
            "remarks": report.remarks,
        })

    # Leave-type reports (week off / leave / company holiday / comp-off) carry no
    # task lines, so the task join above skips them. Surface each as a single
    # day-status-only row — Day Status + Day Remarks filled, every activity
    # column blank — so the PM still sees the employee was off that day, both in
    # the dashboard preview and the Excel export. Skipped when filtering by a
    # task attribute (project / activity / sub-activity), since a no-activity day
    # can never match those.
    if project_id is None and activity_id is None and sub_activity_id is None:
        nq = (
            select(DailyWorkReport, Employee)
            .join(Employee, Employee.id == DailyWorkReport.employee_id)
            .where(
                DailyWorkReport.id.in_(scoped),
                ~select(WorkReportTask.id)
                .where(WorkReportTask.report_id == DailyWorkReport.id)
                .exists(),
            )
        )
        if employee_id is not None:
            nq = nq.where(DailyWorkReport.employee_id == employee_id)
        if date_from is not None:
            nq = nq.where(DailyWorkReport.report_date >= date_from)
        if date_to is not None:
            nq = nq.where(DailyWorkReport.report_date <= date_to)
        for report, emp in db.execute(nq).all():
            rows.append({
                "employee_label": f"{emp.employee_code} - {emp.full_name}",
                "report_date": report.report_date,
                "day_status": (
                    DAY_STATUS_LABELS.get(report.day_status.value, report.day_status.value)
                    if report.day_status
                    else None
                ),
                "project_code": None,
                "activity_type": None,
                "sub_activity_type": None,
                "tags": None,
                "docs": None,
                "bom": None,
                "spares": None,
                "remarks": report.remarks,
            })

    # Keep employee+date rows contiguous so the groupby in build_activity_groups
    # forms correct groups and leave days interleave chronologically (stable sort
    # preserves task order within a day).
    rows.sort(key=lambda r: (r["employee_label"], r["report_date"]))
    return rows


def build_activity_groups(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    activity_id: uuid.UUID | None = None,
    sub_activity_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict:
    """Group the flat activity rows by Employee + Date into one row each, and
    report the max activities on any single Employee+Date (drives the dynamic
    activity-column count). Single source for the preview and the Excel export —
    multiple activities on a day fill additional column groups on the same row."""
    rows = build_activity_rows(
        db,
        actor,
        employee_id=employee_id,
        project_id=project_id,
        activity_id=activity_id,
        sub_activity_id=sub_activity_id,
        date_from=date_from,
        date_to=date_to,
    )

    max_activities = 0
    out_rows: list[dict] = []
    # rows are ordered by employee_code, report_date, task id → contiguous groups.
    for (emp_label, report_date), day_rows in groupby(
        rows, key=lambda r: (r["employee_label"], r["report_date"])
    ):
        day_rows = list(day_rows)
        # A leave-type day contributes one day-status-only row with no activity
        # (project/activity/sub all empty) — keep it out of the activities list
        # so the day shows with Day Status + Remarks but zero activities.
        activities = [
            {
                "project_code": r["project_code"],
                "activity_type": r["activity_type"],
                "sub_activity_type": r["sub_activity_type"],
                "tags": r["tags"],
                "docs": r["docs"],
                "bom": r["bom"],
                "spares": r["spares"],
            }
            for r in day_rows
            if r["project_code"] is not None
            or r["activity_type"] is not None
            or r["sub_activity_type"] is not None
        ]
        max_activities = max(max_activities, len(activities))
        out_rows.append({
            "employee_label": emp_label,
            "report_date": report_date,
            "day_status": day_rows[0]["day_status"],
            "remarks": day_rows[0]["remarks"],
            "activities": activities,
        })

    return {"max_activities": max_activities or 1, "rows": out_rows}


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

    # Leave-type day statuses (week off / leave / company holiday / comp-off)
    # mean no project work was done — the report carries no task lines and is
    # exempt from benchmark/overdue tracking. Any tasks the client sent are
    # ignored; a working-day status still requires at least one activity.
    no_activity = data.day_status in NO_ACTIVITY_DAY_STATUSES
    tasks = [] if no_activity else list(data.tasks)
    if not no_activity and not tasks:
        raise AppError(
            "validation_error",
            "Add at least one activity, or choose a leave-type day status.",
            422,
        )
    total, snapshots = _validate_tasks(db, me.id, tasks)

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
    for task, snap in zip(tasks, snapshots):
        started_date, due_date = _task_based_dates(data.report_date, snap)
        db.add(
            WorkReportTask(
                report_id=report.id,
                project_id=task.project_id,
                description=task.description,
                minutes_spent=task.minutes_spent,
                task_minutes_spent=task.task_minutes_spent,
                activity_type=snap["activity_type"],
                tags_count=task.tags_count,
                docs_count=task.docs_count,
                bom_count=task.bom_count,
                spares_count=task.spares_count,
                sub_activity_id=task.sub_activity_id,
                sub_activity_name=snap["sub_activity_name"],
                activity_name=snap["activity_name"],
                started_date=started_date,
                due_date=due_date,
                is_completed=task.is_completed,
                completed_date=_today() if task.is_completed else None,
                maintenance_plant_id=task.maintenance_plant_id,
                maintenance_plant_code=snap["maintenance_plant_code"],
                maintenance_plant_description=snap["maintenance_plant_description"],
                planning_plant_code=snap["planning_plant_code"],
                planning_plant_description=snap["planning_plant_description"],
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

    # A leave-type day status (current or being set in this update) means the
    # report carries no project work: drop any task lines and zero the total,
    # regardless of what tasks the client sent.
    effective_day_status = data.day_status if "day_status" in fields else report.day_status
    no_activity = effective_day_status in NO_ACTIVITY_DAY_STATUSES

    if no_activity:
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        report.total_minutes = 0
    elif "tasks" in fields and data.tasks is not None:
        total, snapshots = _validate_tasks(db, me.id, data.tasks)
        # Preserve completed_date across a full task-row replace: re-saving a
        # report (e.g. for an unrelated field) shouldn't reset an
        # already-completed TASK_BASED row's completion date to "today"
        # every time. Keyed by sub_activity_id since rows have no other
        # stable identity across a delete+recreate.
        old_completed_dates: dict[uuid.UUID, date] = {
            row.sub_activity_id: row.completed_date
            for row in db.execute(
                select(WorkReportTask).where(
                    WorkReportTask.report_id == report.id,
                    WorkReportTask.is_completed.is_(True),
                    WorkReportTask.sub_activity_id.is_not(None),
                )
            ).scalars()
        }
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        for task, snap in zip(data.tasks, snapshots):
            started_date, due_date = _task_based_dates(report.report_date, snap)
            completed_date = None
            if task.is_completed:
                completed_date = old_completed_dates.get(task.sub_activity_id) or _today()
            db.add(
                WorkReportTask(
                    report_id=report.id,
                    project_id=task.project_id,
                    description=task.description,
                    minutes_spent=task.minutes_spent,
                    task_minutes_spent=task.task_minutes_spent,
                    activity_type=snap["activity_type"],
                    tags_count=task.tags_count,
                    docs_count=task.docs_count,
                    bom_count=task.bom_count,
                    spares_count=task.spares_count,
                    sub_activity_id=task.sub_activity_id,
                    sub_activity_name=snap["sub_activity_name"],
                    activity_name=snap["activity_name"],
                    started_date=started_date,
                    due_date=due_date,
                    is_completed=task.is_completed,
                    completed_date=completed_date,
                    maintenance_plant_id=task.maintenance_plant_id,
                    maintenance_plant_code=snap["maintenance_plant_code"],
                    maintenance_plant_description=snap["maintenance_plant_description"],
                    planning_plant_code=snap["planning_plant_code"],
                    planning_plant_description=snap["planning_plant_description"],
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


def update_task_completion(
    db: Session, actor: User, task_id: uuid.UUID, data: TaskCompletionUpdate
) -> WorkReportTask:
    """Toggle a TASK_BASED row's completion checkbox — independent of the
    parent report's status (draft/submitted/rejected/granted). These
    activities often complete days after the report they were logged on is
    already submitted/locked, so this deliberately bypasses the normal
    locked-report edit restriction; it only ever touches
    is_completed/completed_date on this one row, nothing else."""
    row = db.get(WorkReportTask, task_id)
    if row is None:
        raise AppError("not_found", "Task not found.", 404)
    report = db.get(DailyWorkReport, row.report_id)
    if report is None:
        raise AppError("not_found", "Task not found.", 404)
    _assert_author(db, actor, report)

    row.is_completed = data.is_completed
    row.completed_date = _today() if data.is_completed else None
    db.add(row)
    db.commit()
    db.refresh(row)
    row.is_overdue, row.days_overdue = compute_overdue(row.due_date, row.is_completed, _today())
    return row


_COUNT_FIELD_COLUMNS = {
    "tags": "tags_count",
    "docs": "docs_count",
    "bom": "bom_count",
    "spares": "spares_count",
}


def _apply_benchmarks(db: Session, report: DailyWorkReport) -> None:
    """Freeze benchmark snapshot + compute deficit/productivity_pct for every
    task row with a NUMERIC sub-activity. Runs once, at submit time only — never
    on draft save, and recomputed (overwriting prior values) on every
    resubmission, since a resubmit implies the underlying count may have
    changed.

    The "actual" value is read straight off whichever of
    tags_count/docs_count/bom_count/spares_count the sub-activity's
    relevant_count_field names — there is no separate actual-count field, so
    the same production number is never entered twice.

    Benchmark shortfall/overdue alerts are NOT persisted here — they're
    computed live, on demand, by activity_master.service.get_daily_benchmark_ledger
    / get_overdue_activities (see the dashboard + login-alert endpoints).
    Persisting a notification at submit time would create a second, staler
    source of truth alongside those live queries."""
    # On a half day the employee worked half the time, so every NUMERIC target
    # is halved (benchmark 100 -> 50) before the deficit/productivity math.
    half_day = report.day_status == DayStatus.half_day
    rows = db.execute(
        select(WorkReportTask).where(WorkReportTask.report_id == report.id)
    ).scalars().all()
    for row in rows:
        if row.sub_activity_id is None:
            continue
        sub = db.get(ActivityMaster, row.sub_activity_id)
        if sub is None:
            continue
        benchmark_value = sub.benchmark_value
        if half_day and benchmark_value is not None:
            benchmark_value = benchmark_value / 2
        row.benchmark_type_snapshot = sub.benchmark_type
        row.benchmark_value_snapshot = benchmark_value
        row.benchmark_period_days_snapshot = sub.benchmark_period_days
        row.relevant_count_field_snapshot = sub.relevant_count_field
        actual_value = None
        if sub.relevant_count_field:
            column = _COUNT_FIELD_COLUMNS.get(sub.relevant_count_field)
            actual_value = getattr(row, column) if column else None
        deficit, productivity_pct = compute_benchmark(
            sub.benchmark_type, benchmark_value, actual_value
        )
        row.deficit = deficit
        row.productivity_pct = productivity_pct
        db.add(row)


def submit_work_report(
    db: Session, actor: User, report_id: uuid.UUID
) -> DailyWorkReport:
    report = _fetch(db, report_id)
    _assert_author(db, actor, report)
    if report.status not in _EDITABLE:
        raise AppError(
            "validation_error", "Only draft or rejected reports can be submitted.", 422
        )
    # Leave-type days (week off / leave / company holiday / comp-off) legitimately
    # carry no task lines — only working days must have at least one activity.
    if report.day_status not in NO_ACTIVITY_DAY_STATUSES:
        has_task = db.execute(
            select(WorkReportTask.id).where(WorkReportTask.report_id == report.id).limit(1)
        ).scalar_one_or_none()
        if has_task is None:
            raise AppError("validation_error", "Add at least one task before submitting.", 422)

    _apply_benchmarks(db, report)
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
