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
from decimal import Decimal
from itertools import groupby

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import authz
from app.core.config import settings
from app.modules.activity_master.models import (
    COUNT_FIELD_BY_UNIT,
    LEVEL_SUB_ACTIVITY,
    TASK_BENCHMARK_TYPES,
    VALID_COUNT_FIELDS,
    ActivityMaster,
    is_lumpsum_unit_row,
)
from app.modules.activity_master import access_service
from app.modules.activity_master.benchmark_exception import (
    VALID_BENCHMARK_EXCEPTION_CODES,
    is_eligible_row,
    is_valid_exception,
)
from app.modules.activity_master.service import (
    compute_benchmark,
    compute_overdue,
    scaled_target,
)
from app.modules.work_reports import work_items as wi
from app.modules.employees.models import Employee, EmployeeStatus
from app.modules.employees.service import _current_employee
from app.modules.job_codes.models import JobCode
from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.modules.projects.models import (
    Project,
    ProjectMember,
    ProjectStatus,
)
from app.modules.users.models import User, UserRole
from app.modules.work_reports.models import (
    DAY_PART_FRACTIONS,
    NO_ACTIVITY_DAY_STATUSES,
    DailyWorkReport,
    DayPart,
    DayStatus,
    ReportMode,
    WorkReportPeriod,
    WorkReportStatus,
    WorkReportTask,
)
from app.modules.work_reports.schemas import (
    TaskCompletionUpdate,
    WorkReportCreate,
    WorkReportEditRequest,
    WorkReportPeriodIn,
    WorkReportStatusFilter,
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


def _notify_author(db: Session, report: DailyWorkReport, type_: str, title: str,
                   message: str) -> None:
    author = db.get(Employee, report.employee_id)
    if author is None or author.user_id is None:
        return
    _push(db, author.user_id, type_, title, message, report.id,
          f"/work-reports/{report.id}")


def _notify_project_heads(db: Session, report: DailyWorkReport, author: Employee,
                          type_: str, title: str, message: str) -> None:
    """Notify the Project Head of each of the report's projects — and only them.
    The Head owns report review, so an edit request goes solely to the Head;
    the PM and the author's manager are never notified. (Requires report.tasks
    to be attached.)"""
    url = f"/work-reports/{report.id}"
    project_ids = {t.project_id for t in getattr(report, "tasks", [])}
    if not project_ids:
        return
    head_emp_ids = db.execute(
        select(Project.head_employee_id).where(
            Project.id.in_(project_ids),
            Project.head_employee_id.is_not(None),
        )
    ).scalars().all()
    for emp_id in set(head_emp_ids):
        if emp_id == author.id:
            continue
        head = db.get(Employee, emp_id)
        if head and head.user_id:
            _push(db, head.user_id, type_, title, message, report.id, url)


_EDITABLE = {
    WorkReportStatus.draft,
    WorkReportStatus.rejected,
    WorkReportStatus.granted,
}


def _led_rows_filter(pairs: set[tuple[uuid.UUID, uuid.UUID]]):
    """Row-level SQL condition: the task row belongs to an exact
    (project_id, parent activity_id) combination the actor Leads. The row's
    sub_activity_id resolves to its Activity Master parent for the comparison;
    rows with no sub_activity_id (or a dangling one) never match — a row
    without a reliable Activity Master mapping is never exposed through Lead
    scope, and text-name columns are never consulted."""
    return or_(*(
        and_(
            WorkReportTask.project_id == project_id,
            WorkReportTask.sub_activity_id.in_(
                select(ActivityMaster.id).where(ActivityMaster.parent_id == activity_id)
            ),
        )
        for project_id, activity_id in pairs
    ))


def _led_report_ids(pairs: set[tuple[uuid.UUID, uuid.UUID]]):
    """Subquery: ids of reports carrying at least one led-activity task row."""
    return select(WorkReportTask.report_id).where(_led_rows_filter(pairs))


def _report_has_led_task(db: Session, actor: User, report_id: uuid.UUID) -> bool:
    pairs = authz.led_activity_pairs(db, actor)
    if not pairs:
        return False
    return db.execute(
        select(WorkReportTask.id).where(
            WorkReportTask.report_id == report_id,
            _led_rows_filter(pairs),
        ).limit(1)
    ).scalar_one_or_none() is not None


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

    can_review = the Project Head of one of the report's projects may grant edit
    access on it (but never on one's own report — authors request edits, they
    don't grant them). The PM does not grant edit access, so this is Head-only.
    """
    _attach_tasks(db, reports)
    # Resolve author display names server-side so scoped viewers (project Heads)
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
    me = _current_employee(db, actor)
    reviewable = authz.reviewable_project_ids(db, actor)
    for r in reports:
        r.scoped_to_led_activities = False
    # Activity-Lead row scoping: a foreign report visible only through a Lead
    # assignment is trimmed to its led rows BEFORE the flags below, so
    # can_review (Head-only, and False for such reports anyway) never reads
    # rows the viewer isn't allowed to see.
    if actor.role != UserRole.project_manager and me is not None:
        _restrict_to_led_rows(db, actor, me.id, reviewable, reports)
    # Periods are attached AFTER the Lead row-trim so a Lead-scoped report's
    # periods expose only the led rows (period metadata itself is not secret).
    _attach_periods(db, reports)
    for r in reports:
        r.can_review = (
            me is not None
            and r.employee_id != me.id
            and any(t.project_id in reviewable for t in r.tasks)
        )
        # The current Project Head of one of the report's own projects may edit
        # their OWN submitted report directly — no request-edit/grant-edit
        # handshake (they'd otherwise be the report's only reviewer, and no one
        # may grant edit on their own report). Derived from the same
        # `reviewable` set as can_review, so the UI and the write-side guard in
        # update_work_report agree.
        r.can_self_edit = (
            me is not None
            and r.employee_id == me.id
            and r.status == WorkReportStatus.submitted
            and any(t.project_id in reviewable for t in r.tasks)
        )
    return reports


def _restrict_to_led_rows(
    db: Session,
    actor: User,
    me_id: uuid.UUID,
    reviewable: set[uuid.UUID],
    reports: list[DailyWorkReport],
) -> None:
    """Trim Activity-Lead-scoped reports to just their led task rows.

    A report the viewer reaches ONLY through a Lead assignment (not their own,
    not from a project they Head) must expose only the task rows whose exact
    (project, parent activity) pair the viewer Leads — never the rest of a
    mixed-activity report. Own and Head-scoped reports keep every row. Reports
    that lose rows get `scoped_to_led_activities = True` so the UI can say the
    view is partial. Requires `.tasks` to be attached."""
    foreign = [
        r for r in reports
        if r.employee_id != me_id
        and not any(t.project_id in reviewable for t in r.tasks)
    ]
    if not foreign:
        return
    pairs = authz.led_activity_pairs(db, actor)
    sub_ids = {
        t.sub_activity_id for r in foreign for t in r.tasks
        if t.sub_activity_id is not None
    }
    parent_of: dict[uuid.UUID, uuid.UUID | None] = {}
    if pairs and sub_ids:
        parent_of = dict(db.execute(
            select(ActivityMaster.id, ActivityMaster.parent_id).where(
                ActivityMaster.id.in_(sub_ids)
            )
        ).all())
    for r in foreign:
        kept = [
            t for t in r.tasks
            if t.sub_activity_id is not None
            and (t.project_id, parent_of.get(t.sub_activity_id)) in pairs
        ]
        if len(kept) != len(r.tasks):
            r.scoped_to_led_activities = True
        r.tasks = kept


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


def _lifecycle_row_kwargs(
    db: Session,
    report: DailyWorkReport,
    task,
    snap: dict,
    *,
    seen: set,
    legacy_completed_dates: dict | None = None,
    existing_links: set | None = None,
) -> dict:
    """started_date/due_date/is_completed/completed_date/work_item_id for one
    saved task row.

    Work-item flow (task continuation) when the feature flag is ON and the row's
    sub-activity is TASK_BASED — the row links to a persistent WorkItem with a
    fixed deadline. Otherwise the exact legacy standalone behaviour: per-row
    dates from _task_based_dates, completion stamped on the row itself, no work
    item. A saved report being edited is always an editable draft here, so
    completion corrections are allowed (editable=True). `existing_links` are the
    work items this report already linked before the save (empty on create)."""
    if (
        settings.TASK_CONTINUATION_ENABLED
        and snap["is_task_based"]
        and getattr(task, "sub_activity_id", None) is not None
    ):
        return wi.resolve_task_work_item(
            db, report=report, task_in=task, snap=snap, editable=True,
            seen=seen, existing_links=existing_links,
        )
    started_date, due_date = _task_based_dates(report.report_date, snap)
    completed_date = None
    if task.is_completed:
        # Preserve an already-stamped completion date across a full row replace
        # (legacy behaviour); default to today for a fresh completion.
        preserved = (
            (legacy_completed_dates or {}).get(getattr(task, "sub_activity_id", None))
        )
        completed_date = preserved or _today()
    return {
        "work_item_id": None,
        "started_date": started_date,
        "due_date": due_date,
        "is_completed": task.is_completed,
        "completed_date": completed_date,
    }


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


def _assert_within_tag_scope(
    db: Session, tasks, *, exclude_report_id: uuid.UUID | None
) -> None:
    """Refuse a report that would push a tag-counted sub-activity past its
    project's estimated tag scope.

    Grouped by (project, sub-activity) BEFORE comparing, because one report can
    carry several rows for the same pairing (split across day parts, or simply
    two lines). Checking each row on its own would let 2 x 400 through against a
    500 remainder.

    Applies only where there is a real ceiling: a TAG_BASED project with an
    established estimate, and a sub-activity whose unit is tags. Everything else
    is unaffected, which is what keeps normal projects and non-tag activities
    behaving exactly as they do today.
    """
    from app.modules.projects import tag_progress

    incoming: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for task in tasks:
        sub_id = getattr(task, "sub_activity_id", None)
        if sub_id is None:
            continue
        count = getattr(task, "tags_count", None) or 0
        if count <= 0:
            continue
        key = (task.project_id, sub_id)
        incoming[key] = incoming.get(key, 0) + count

    for (project_id, sub_id), count in incoming.items():
        project = db.get(Project, project_id)
        sub = db.get(ActivityMaster, sub_id)
        remaining = tag_progress.remaining_tags(
            db, project, sub, exclude_report_id=exclude_report_id
        )
        if remaining is None or count <= remaining:
            continue
        capacity = tag_progress.project_tag_capacity(project)
        raise AppError(
            "validation_error",
            f"\"{sub.name}\" has {remaining} of {capacity} tags left on this "
            f"project. You entered {count}.",
            422,
        )


def _validate_tasks(
    db: Session,
    author_id: uuid.UUID,
    tasks,
    *,
    exclude_report_id: uuid.UUID | None = None,
) -> tuple[int, list[dict]]:
    """Validate project (active) + membership; return (total_minutes, snapshots).

    Each snapshot dict carries the project_name, project_code, and
    project_job_code_code frozen at validation time so they can be written
    directly into the task row for historical accuracy.

    `exclude_report_id` is the report being rewritten, if any — it is left out
    of the tag-scope consumption total so an edit does not count its own
    previous numbers against itself.
    """
    # Restricted-activity enforcement (migration 0061): reject any row selecting
    # a RESTRICTED activity this employee is not authorized for, in a bulk check
    # (never one query per row). Dropdown filtering is not security — this is the
    # server-side gate shared by every write path (create/update/approve). The
    # continuation exception for open work items lives inside this helper.
    access_service.validate_report_activity_access(db, employee_id=author_id, tasks=tasks)

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
        # Narrower than is_task_based: TASK_WITH_QUANTITY is task-bearing but is
        # NOT lump-sum, and the continuation-approval gate keys off this flag
        # alone so quantity tasks are provably never gated.
        is_lumpsum_task = False
        benchmark_period_days: int | None = None
        # Structured benchmark exception (migration 0063). An unknown code is a
        # client error and is rejected outright; a known code on a row whose
        # benchmark configuration cannot carry one is silently CLEARED rather
        # than rejected — same spirit as the count fields, where an irrelevant
        # unit is simply not read. The numbers-based half of the rule (positive
        # target, actual below it) needs the frozen per-period target, which
        # only exists at submit, so it is enforced authoritatively there
        # (_apply_benchmarks). Nothing that reaches the benchmark export
        # bypasses that check.
        exception_code = getattr(task, "benchmark_exception_code", None) or None
        if exception_code is not None and exception_code not in VALID_BENCHMARK_EXCEPTION_CODES:
            raise AppError(
                "validation_error", "Unknown benchmark exception code.", 422
            )
        # Lumpsum count unit (see WorkReportTaskIn.count_field). An unknown name
        # is a client error and is rejected outright — the field ends up naming a
        # real count column, so it is never taken on trust. A known unit on a row
        # whose mode does not let the employee choose one is CLEARED below rather
        # than rejected, exactly as an inapplicable exception code is.
        count_field = getattr(task, "count_field", None) or None
        if count_field is not None and count_field not in VALID_COUNT_FIELDS:
            raise AppError("validation_error", "Unknown count field.", 422)
        # The conditional requirement (mirrored in the form's own schema, which
        # blocks the save first for a usable message). A count that has been
        # entered must say which field it belongs to; the server will not guess
        # a column for it. Checked against what the CLIENT sent, before the
        # clearing rules below, so an unattributed number is never quietly
        # dropped. `or None` is deliberate: 0 is no count, not a count of zero.
        count_value = getattr(task, "count_value", None) or None
        if count_value is not None and count_field is None:
            raise AppError(
                "validation_error",
                "Please select a field for the entered count.",
                422,
            )
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
            # Every TASK mode gets a due date + completion + carry-forward: the
            # legacy TASK_BASED, TASK_STATUS_ONLY, and TASK_WITH_QUANTITY (whose
            # quantity side is handled separately by the benchmark calc — having
            # a quantity does not stop it being a deadline-bearing task).
            is_task_based = sub.benchmark_type in TASK_BENCHMARK_TYPES
            is_lumpsum_task = is_lumpsum_unit_row(
                sub.benchmark_type, sub.relevant_count_field
            )
            benchmark_period_days = sub.benchmark_period_days
            # Only a lumpsum row carries an employee-chosen unit. A quantity
            # mode's unit is a property of its benchmark (Activity Master's
            # relevant_count_field) and is frozen at submit by _apply_benchmarks,
            # so anything sent for one of those is dropped here.
            if not is_lumpsum_unit_row(sub.benchmark_type, sub.relevant_count_field):
                count_field = None
                count_value = None
            # Clear an exception the selected sub-activity cannot carry: a task
            # mode, or a counted unit outside the eligible set (Phase 1: TAGS).
            if exception_code is not None and not is_eligible_row(
                sub.benchmark_type, sub.relevant_count_field
            ):
                exception_code = None
        else:
            # No Activity Master selection at all — nothing to benchmark, so
            # nothing to except, and no mode that could take a chosen unit.
            exception_code = None
            count_field = None
            count_value = None
            is_lumpsum_task = False
        # A named field with nothing counted against it is not a state worth
        # storing: it would restore as a picked field with an empty Count and
        # export an artificial 0 under that column. Selecting a field is only
        # ever a statement ABOUT a count, so with no count it is simply dropped
        # — the row stays valid and saves, which is what an activity with
        # nothing to count needs.
        if count_field is not None:
            column = COUNT_FIELD_BY_UNIT[count_field]
            resolved = (
                count_value if count_value is not None else getattr(task, column, 0)
            )
            if not resolved:
                count_field = None
                count_value = None
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
            "is_lumpsum_task": is_lumpsum_task,
            "benchmark_period_days": benchmark_period_days,
            "benchmark_exception_code": exception_code,
            "count_field": count_field,
            "count_value": count_value,
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
    # Last, and across the whole task list rather than per row — see the helper.
    _assert_within_tag_scope(db, tasks, exclude_report_id=exclude_report_id)
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
    report_by_id = {r.id: r for r in reports}
    today = _today()
    # day_part per row (display): resolved from the row's period link.
    period_parts: dict[uuid.UUID, str] = {}
    pids = {row.period_id for row in rows if row.period_id is not None}
    if pids:
        period_parts = dict(db.execute(
            select(WorkReportPeriod.id, WorkReportPeriod.day_part).where(
                WorkReportPeriod.id.in_(pids)
            )
        ).all())
    # Batched reads for the work-item-linked rows: the items themselves, the
    # latest linked entry date per item (completion is only offered on the most
    # recent report), and the report where each completed item was completed.
    item_ids = {row.work_item_id for row in rows if row.work_item_id is not None}
    items: dict[uuid.UUID, wi.WorkItem] = {}
    latest_entry_date: dict[uuid.UUID, date] = {}
    completion_rids: dict[uuid.UUID, uuid.UUID] = {}
    if item_ids:
        items = {
            it.id: it
            for it in db.execute(
                select(wi.WorkItem).where(wi.WorkItem.id.in_(item_ids))
            ).scalars()
        }
        for iid, d in db.execute(
            select(WorkReportTask.work_item_id, func.max(DailyWorkReport.report_date))
            .join(DailyWorkReport, DailyWorkReport.id == WorkReportTask.report_id)
            .where(WorkReportTask.work_item_id.in_(item_ids))
            .group_by(WorkReportTask.work_item_id)
        ).all():
            latest_entry_date[iid] = d
        completion_rids = wi.completion_report_ids(db, item_ids)
    for row in rows:
        # Transient, computed fresh on every read (never stored) — same
        # pattern as report.can_review below.
        row.day_part = period_parts.get(row.period_id)
        row.is_overdue, row.days_overdue = compute_overdue(row.due_date, row.is_completed, today)
        row.work_item_lifecycle = None
        # Explicit daily vs overall completion fields (default: legacy / non-item).
        row.row_is_completed = bool(row.is_completed)
        row.row_completed_date = row.completed_date
        row.overall_completed_on = None
        row.overall_lifecycle = None
        row.completed_on_this_report = False
        row.completion_report_id = None
        row.can_complete_here = None
        item = items.get(row.work_item_id) if row.work_item_id else None
        if item is not None:
            report = report_by_id.get(row.report_id)
            row.work_item_lifecycle = wi.lifecycle_of(
                item.due_date, item.completed_on, today=today
            ).value
            row.overall_lifecycle = row.work_item_lifecycle
            row.overall_completed_on = item.completed_on
            row.completion_report_id = completion_rids.get(item.id)
            row.completed_on_this_report = (
                item.completed_on is not None
                and report is not None
                and report.report_date == item.completed_on
            )
            # Active completion control only when the task is open, this report is
            # editable, and this is the latest linked entry (no later report to
            # backdate over). Earlier/older linked rows get a read-only view.
            is_latest = (
                report is not None
                and latest_entry_date.get(item.id) == report.report_date
            )
            row.can_complete_here = (
                item.completed_on is None
                and report is not None
                and report.status in _EDITABLE
                and is_latest
            )
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
    A Head sees own reports (all statuses) + submitted/rejected/granted reports
    from projects they head, so they can still track a report they sent
    back or granted edit access to, not just the moment it's re-submitted.
    An Activity Lead additionally sees submitted/rejected/granted reports that
    carry at least one task row on an activity they Lead (never drafts); the
    row-level trim to just those led rows happens in _decorate /
    build_activity_rows — this report-level scope only decides which report
    headers are visible at all. Permissions are additive (own OR Head OR Lead).
    Everyone else (contributors/QC) sees only their own reports (all statuses).
    """
    if actor.role == UserRole.project_manager:
        return stmt.where(DailyWorkReport.status != WorkReportStatus.draft), True
    me = _current_employee(db, actor)
    if me is None:
        return stmt, False
    conds = [DailyWorkReport.employee_id == me.id]
    # Head sees reviewable reports from projects they head.
    scoped_ids = authz.reviewable_project_ids(db, actor)
    if scoped_ids:
        scoped_reports = select(WorkReportTask.report_id).where(
            WorkReportTask.project_id.in_(scoped_ids)
        )
        conds.append(and_(
            DailyWorkReport.id.in_(scoped_reports),
            DailyWorkReport.status.in_(_REVIEWABLE),
        ))
    # Activity Lead sees non-draft reports containing a led-activity row.
    led_pairs = authz.led_activity_pairs(db, actor)
    if led_pairs:
        conds.append(and_(
            DailyWorkReport.id.in_(_led_report_ids(led_pairs)),
            DailyWorkReport.status.in_(_REVIEWABLE),
        ))
    if len(conds) == 1:
        return stmt.where(conds[0]), True
    return stmt.where(or_(*conds)), True


def list_work_reports(
    db: Session,
    actor: User,
    *,
    employee_id: uuid.UUID | None,
    project_id: uuid.UUID | None,
    status: WorkReportStatusFilter | None,
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
        # "requested" and "submitted" are two views of the same persisted
        # `submitted` status, split on whether an edit request is pending — so
        # the count/pagination subquery below stays exact for either. Every
        # other value maps 1:1 to the stored status.
        if status == WorkReportStatusFilter.requested:
            stmt = stmt.where(
                DailyWorkReport.status == WorkReportStatus.submitted,
                DailyWorkReport.edit_requested_at.is_not(None),
            )
        elif status == WorkReportStatusFilter.submitted:
            stmt = stmt.where(
                DailyWorkReport.status == WorkReportStatus.submitted,
                DailyWorkReport.edit_requested_at.is_(None),
            )
        else:
            stmt = stmt.where(DailyWorkReport.status == WorkReportStatus(status.value))
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
        select(WorkReportTask, DailyWorkReport, Employee, WorkReportPeriod)
        .join(DailyWorkReport, DailyWorkReport.id == WorkReportTask.report_id)
        .join(Employee, Employee.id == DailyWorkReport.employee_id)
        # Left join to the task's period so the split-day activity blocks can be
        # ordered First Half then Second Half deterministically, independent of
        # task creation order (see the order_by below). The period is also
        # SELECTED, not merely joined: the export's HALF column and its per-half
        # Day Status read day_part / period_status straight off it. Nullable for
        # legacy rows.
        .outerjoin(WorkReportPeriod, WorkReportPeriod.id == WorkReportTask.period_id)
        .where(WorkReportTask.report_id.in_(scoped))
    )
    # Row-level trim mirroring _restrict_to_led_rows: within the scoped
    # reports, a non-PM sees a task row only when the report is their own, the
    # report touches a project they Head (Head keeps the full report), or the
    # row itself is on a led (project, activity) pair. Applied in SQL so the
    # preview and the Excel export share the exact same scoped data, and no
    # supplied filter parameter can widen it (filters below only AND-narrow).
    if actor.role != UserRole.project_manager:
        me = _current_employee(db, actor)
        row_conds = [DailyWorkReport.employee_id == me.id]
        head_ids = authz.reviewable_project_ids(db, actor)
        if head_ids:
            row_conds.append(
                DailyWorkReport.id.in_(
                    select(WorkReportTask.report_id).where(
                        WorkReportTask.project_id.in_(head_ids)
                    )
                )
            )
        led_pairs = authz.led_activity_pairs(db, actor)
        if led_pairs:
            row_conds.append(_led_rows_filter(led_pairs))
        q = q.where(or_(*row_conds))
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
    # First Half before Second Half (Full-Day / legacy NULL period rank as 0 and
    # keep their existing task-id order). Task id breaks ties within a part.
    part_rank = case(
        (WorkReportPeriod.day_part == DayPart.first_half.value, 1),
        (WorkReportPeriod.day_part == DayPart.second_half.value, 2),
        else_=0,
    )
    q = q.order_by(
        Employee.employee_code, DailyWorkReport.report_date, part_rank, WorkReportTask.id
    )

    task_result = db.execute(q).all()
    # One combined Day Remarks per report (split-day halves labelled + ordered);
    # dedupe reports so the period lookup runs once per report, not once per task.
    task_reports = {report.id: report for _t, report, _e, _p in task_result}
    remarks_by_report = _combined_remarks_by_report(db, list(task_reports.values()))

    rows: list[dict] = []
    for task, report, emp, period in task_result:
        rows.append({
            "employee_label": f"{emp.employee_code} - {emp.full_name}",
            "report_date": report.report_date,
            "day_status": (
                DAY_STATUS_LABELS.get(report.day_status.value, report.day_status.value)
                if report.day_status
                else None
            ),
            # The half this activity belongs to ('first_half' / 'second_half' /
            # 'full_day'), and that half's OWN status when a split day mixes two
            # (worked first half, leave second half). Both are read-only
            # passthroughs of what the period already records — the report-level
            # day_status above is left exactly as it was.
            "day_part": period.day_part if period is not None else None,
            "period_status": (
                DAY_STATUS_LABELS.get(
                    period.period_status.value, period.period_status.value
                )
                if period is not None and period.period_status
                else None
            ),
            "project_code": task.project_code,
            "activity_type": task.activity_name,
            "sub_activity_type": task.sub_activity_name,
            "tags": task.tags_count,
            "docs": task.docs_count,
            "bom": task.bom_count,
            "spares": task.spares_count,
            "pages": task.pages_count,
            "records": task.records_count,
            # Benchmark as FROZEN on the task at submit time (_apply_benchmarks) —
            # the mode, the effective per-period target and the unit it is counted
            # in. Nothing is computed here: the export only renders these three.
            "benchmark_type": task.benchmark_type_snapshot,
            "benchmark_value": task.benchmark_value_snapshot,
            "benchmark_unit": task.relevant_count_field_snapshot,
            "remarks": remarks_by_report[report.id],
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
        leave_result = db.execute(nq).all()
        leave_remarks = _combined_remarks_by_report(
            db, [report for report, _emp in leave_result]
        )
        for report, emp in leave_result:
            rows.append({
                "employee_label": f"{emp.employee_code} - {emp.full_name}",
                "report_date": report.report_date,
                "day_status": (
                    DAY_STATUS_LABELS.get(report.day_status.value, report.day_status.value)
                    if report.day_status
                    else None
                ),
                "day_part": None,
                "period_status": None,
                "project_code": None,
                "activity_type": None,
                "sub_activity_type": None,
                "tags": None,
                "docs": None,
                "bom": None,
                "spares": None,
                "pages": None,
                "records": None,
                "benchmark_type": None,
                "benchmark_value": None,
                "benchmark_unit": None,
                "remarks": leave_remarks[report.id],
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
                "day_part": r["day_part"],
                "period_status": r["period_status"],
                "project_code": r["project_code"],
                "activity_type": r["activity_type"],
                "sub_activity_type": r["sub_activity_type"],
                "tags": r["tags"],
                "docs": r["docs"],
                "bom": r["bom"],
                "spares": r["spares"],
                "pages": r["pages"],
                "records": r["records"],
                "benchmark_type": r["benchmark_type"],
                "benchmark_value": r["benchmark_value"],
                "benchmark_unit": r["benchmark_unit"],
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
    if _report_in_projects(db, report.id, authz.reviewable_project_ids(db, actor)):
        return
    # Activity Lead: non-draft reports carrying a led-activity row. The
    # response is trimmed to just those rows in _decorate — direct detail
    # access can never reveal the unrelated rows of a mixed report.
    if report.status in _REVIEWABLE and _report_has_led_task(db, actor, report.id):
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


def get_open_tasks(db: Session, actor: User, report_date: date) -> list[dict]:
    """Unfinished work items the acting employee can continue in a report dated
    `report_date` (lifecycle evaluated relative to that date). Empty when the
    feature is off or the actor has no employee profile — legacy NULL-linked
    rows are never surfaced here."""
    if not settings.TASK_CONTINUATION_ENABLED:
        return []
    me = _current_employee(db, actor)
    if me is None:
        return []
    return wi.get_open_work_items(db, employee_id=me.id, report_date=report_date)


def get_report_scope(db: Session, actor: User) -> dict:
    """Filter metadata for the reports view — the minimum the employee filter
    needs, NOT a widening of /employees (which stays RBAC-limited).

    Head/Lead employees get their accessible projects, the activities they Lead
    per project (empty list = whole project, i.e. Head access), and each
    project's active members. PMs get empty scope — they already have the
    org-wide employee filter client-side. Purely informational for the UI: the
    report list / export queries enforce the same scope server-side regardless
    of what the client sends."""
    empty = {"is_project_head": False, "is_activity_lead": False, "projects": []}
    if actor.role == UserRole.project_manager:
        return empty
    me = _current_employee(db, actor)
    if me is None:
        return empty
    head_ids = authz.reviewable_project_ids(db, actor)
    led_pairs = authz.led_activity_pairs(db, actor)
    if not head_ids and not led_pairs:
        return empty
    led_by_project: dict[uuid.UUID, set[uuid.UUID]] = {}
    for project_id, activity_id in led_pairs:
        led_by_project.setdefault(project_id, set()).add(activity_id)
    projects = db.execute(
        select(Project).where(
            Project.id.in_(set(head_ids) | set(led_by_project)),
            Project.deleted_at.is_(None),
            Project.status != ProjectStatus.archived,
        ).order_by(Project.name)
    ).scalars().all()
    activity_ids = {a for ids in led_by_project.values() for a in ids}
    activity_names: dict[uuid.UUID, str] = {}
    if activity_ids:
        activity_names = dict(db.execute(
            select(ActivityMaster.id, ActivityMaster.name).where(
                ActivityMaster.id.in_(activity_ids)
            )
        ).all())
    out_projects = []
    for project in projects:
        members = db.execute(
            select(Employee)
            .join(ProjectMember, ProjectMember.employee_id == Employee.id)
            .where(
                ProjectMember.project_id == project.id,
                Employee.status == EmployeeStatus.active,
                Employee.deleted_at.is_(None),
            ).order_by(Employee.first_name, Employee.last_name)
        ).scalars().all()
        is_head = project.id in head_ids
        led_here = [] if is_head else sorted(
            led_by_project.get(project.id, set()),
            key=lambda a: activity_names.get(a, ""),
        )
        out_projects.append({
            "project_id": project.id,
            "code": project.code,
            "name": project.name,
            "access": "head" if is_head else "lead",
            "activities": [
                {"activity_id": a, "name": activity_names.get(a)} for a in led_here
            ],
            "members": [
                {"employee_id": e.id, "employee_code": e.employee_code, "name": e.full_name}
                for e in members
            ],
        })
    return {
        "is_project_head": bool(head_ids),
        "is_activity_lead": bool(led_pairs),
        "projects": out_projects,
    }


# ---------- periods (Full-Day / Split-Day, migration 0060) -----------------
_DAY_PART_ORDER = {
    DayPart.full_day.value: 0,
    DayPart.first_half.value: 1,
    DayPart.second_half.value: 2,
}
_HALF_PARTS = {DayPart.first_half, DayPart.second_half}

_DAY_PART_LABELS = {
    DayPart.full_day.value: "Full Day",
    DayPart.first_half.value: "First Half",
    DayPart.second_half.value: "Second Half",
}


def format_report_remarks(
    report_mode: str,
    header_remarks: str | None,
    period_remarks: dict[str, str | None],
) -> str:
    """Combined Day Remarks for the PM Weekly Activity Report preview + Excel
    export, from the report's AUTHORITATIVE remark source(s).

    Full-day: the header remark verbatim (whitespace-trimmed), no prefix.
    Split-day: each half owns its OWN period remark (work_report_periods.remarks).
    Both are labelled and ordered First Half then Second Half regardless of task
    or DB return order, one per line, joined by a single newline. A blank half
    contributes no line (no empty label); both blank -> "". Internal text is
    preserved, and identical first/second remarks are NOT deduplicated — they
    belong to separate halves.

    `period_remarks` maps day_part -> that period's stored remark; it is empty for
    a full-day report (which never reads it)."""
    if report_mode != ReportMode.split_day.value:
        return (header_remarks or "").strip()
    lines: list[str] = []
    first = (period_remarks.get(DayPart.first_half.value) or "").strip()
    second = (period_remarks.get(DayPart.second_half.value) or "").strip()
    if first:
        lines.append(f"First Half: {first}")
    if second:
        lines.append(f"Second Half: {second}")
    return "\n".join(lines)


def _combined_remarks_by_report(
    db: Session, reports: list[DailyWorkReport]
) -> dict[uuid.UUID, str]:
    """Map report_id -> combined Day Remarks (see format_report_remarks).

    Period remarks are loaded once for the split-day reports only; full-day
    reports use their header remark and need no period query."""
    split_ids = [
        r.id for r in reports if r.report_mode == ReportMode.split_day.value
    ]
    parts: dict[uuid.UUID, dict[str, str | None]] = {}
    if split_ids:
        for rid, day_part, remarks in db.execute(
            select(
                WorkReportPeriod.report_id,
                WorkReportPeriod.day_part,
                WorkReportPeriod.remarks,
            ).where(WorkReportPeriod.report_id.in_(split_ids))
        ).all():
            parts.setdefault(rid, {})[day_part] = remarks
    return {
        r.id: format_report_remarks(r.report_mode, r.remarks, parts.get(r.id, {}))
        for r in reports
    }


def _is_working_status(status: DayStatus | None) -> bool:
    """A period with a leave-type status (or none yet) carries no project work."""
    return status is not None and status not in NO_ACTIVITY_DAY_STATUSES


def _full_day_fraction(status: DayStatus | None) -> tuple[Decimal, bool]:
    """(work_fraction, is_legacy_half_day) for a Full-Day period.

    day_status='half_day' is the LEGACY way of reporting a half-worked day —
    a Full-Day period at fraction 0.5 whose worked half is unknown. Split-day
    reports express the same thing precisely and never use it."""
    if status == DayStatus.half_day:
        return Decimal("0.5"), True
    return Decimal("1.0"), False


def _normalize_periods(
    report_mode: ReportMode | None,
    periods: list[WorkReportPeriodIn] | None,
    *,
    day_status: DayStatus | None,
    location,
    tasks,
) -> dict:
    """Translate either payload shape into one normalized structure.

    Legacy payload (periods is None): one Full-Day period built from the
    header fields — the pre-split behaviour, byte-identical, regardless of the
    feature flag. Periods payload: validated against the split-day invariants;
    split_day additionally requires REPORT_DAY_PARTS_ENABLED.

    Returns {"report_mode", "day_status", "location", "periods": [spec]} where
    each spec is {"day_part", "period_status", "location", "remarks",
    "work_fraction", "is_legacy_half_day", "tasks"} with the fraction always
    SERVER-derived (clients cannot supply one — the schema has no such field).
    Header day_status/location are derived so every legacy reader (exports,
    compliance, reminders, ledger fallback) stays coherent:
      - full-day mode: the period's own status/location;
      - split, one half working: day_status = half_day + the working half's
        location;
      - split, both halves working: the first half's status/location.
    """
    if periods is None:
        # Legacy full-day payload. Leave-type day statuses drop any task lines
        # (existing leniency, unchanged).
        no_activity = day_status in NO_ACTIVITY_DAY_STATUSES
        period_tasks = [] if no_activity else list(tasks or [])
        fraction, legacy_half = _full_day_fraction(day_status)
        if report_mode == ReportMode.split_day:
            raise AppError(
                "validation_error",
                "A split-day report must supply its First-Half and Second-Half periods.",
                422,
            )
        # Header AND period keep the location exactly as sent (legacy parity —
        # the old code never nulled it, even on leave-type days).
        return {
            "report_mode": ReportMode.full_day,
            "day_status": day_status,
            "location": location,
            "periods": [{
                "day_part": DayPart.full_day,
                "period_status": day_status,
                "location": location,
                "remarks": None,
                "work_fraction": fraction,
                "is_legacy_half_day": legacy_half,
                "tasks": period_tasks,
            }],
        }

    parts = [p.day_part for p in periods]
    if len(set(parts)) != len(parts):
        raise AppError("validation_error", "Duplicate reporting periods.", 422)
    part_set = set(parts)
    if part_set == {DayPart.full_day}:
        mode = ReportMode.full_day
    elif part_set == _HALF_PARTS:
        mode = ReportMode.split_day
    else:
        raise AppError(
            "validation_error",
            "A report is either one Full-Day period or exactly a First-Half "
            "and a Second-Half period.",
            422,
        )
    if report_mode is not None and report_mode != mode:
        raise AppError(
            "validation_error", "report_mode does not match the supplied periods.", 422
        )
    if mode == ReportMode.split_day and not settings.REPORT_DAY_PARTS_ENABLED:
        raise AppError("validation_error", "Split-day reports are not enabled.", 422)

    specs: list[dict] = []
    for p in sorted(periods, key=lambda x: _DAY_PART_ORDER[x.day_part.value]):
        if p.day_part in _HALF_PARTS and p.period_status == DayStatus.half_day:
            raise AppError(
                "validation_error",
                "'Half Day' is not a valid status for a half period — pick the "
                "half's own working or leave status.",
                422,
            )
        working = _is_working_status(p.period_status)
        if p.day_part == DayPart.full_day:
            fraction, legacy_half = _full_day_fraction(p.period_status)
        else:
            fraction, legacy_half = DAY_PART_FRACTIONS[p.day_part], False
        period_tasks = list(p.tasks)
        if mode == ReportMode.split_day:
            # A split-day half holds EXACTLY ONE activity while it is working
            # and none while it is not. This is the authoritative guard: the UI
            # offers no way to add a second row, so anything else here is a
            # hand-made or stale payload and is REJECTED rather than trimmed —
            # silently discarding a row would lose work the caller believed it
            # had saved.
            label = _DAY_PART_LABELS.get(p.day_part.value, p.day_part.value)
            if not working and period_tasks:
                raise AppError(
                    "validation_error",
                    f"{label} is not a working half and cannot contain any activity.",
                    422,
                )
            if working and len(period_tasks) > 1:
                raise AppError(
                    "validation_error",
                    f"{label} cannot contain more than one activity — "
                    "Split Day allows exactly one activity per half.",
                    422,
                )
            if working and not period_tasks:
                raise AppError(
                    "validation_error",
                    f"{label} must contain exactly one activity.",
                    422,
                )
        elif not working:
            # Full-Day leave-type period: task lines are dropped, unchanged
            # legacy leniency.
            period_tasks = []
        specs.append({
            "day_part": p.day_part,
            "period_status": p.period_status,
            "location": p.location if working else None,
            "remarks": p.remarks,
            "work_fraction": fraction,
            "is_legacy_half_day": legacy_half,
            "tasks": period_tasks,
        })

    working_specs = [s for s in specs if _is_working_status(s["period_status"])]
    if mode == ReportMode.split_day:
        if not working_specs:
            raise AppError(
                "validation_error",
                "Both halves are non-working — file a Full Day report with the "
                "matching day status instead.",
                422,
            )
        if len(working_specs) == 1:
            header_status = DayStatus.half_day
        else:
            header_status = specs[0]["period_status"]
        header_location = working_specs[0]["location"]
    else:
        header_status = specs[0]["period_status"]
        header_location = specs[0]["location"]

    return {
        "report_mode": mode,
        "day_status": header_status,
        "location": header_location,
        "periods": specs,
    }


def _insert_period_tasks(
    db: Session,
    report: DailyWorkReport,
    period_specs: list[dict],
    snapshots: list[dict],
    *,
    seen_work_items: set,
    legacy_completed_dates: dict | None = None,
    existing_links: set | None = None,
) -> None:
    """Create the period rows + their task rows for a report whose old rows (if
    any) have already been removed. `snapshots` is _validate_tasks output for
    the flattened task list, in period order."""
    snap_iter = iter(snapshots)
    for spec in period_specs:
        period = WorkReportPeriod(
            report_id=report.id,
            day_part=spec["day_part"].value,
            period_status=spec["period_status"],
            location=spec["location"],
            remarks=spec["remarks"],
            work_fraction=spec["work_fraction"],
            is_legacy_half_day=spec["is_legacy_half_day"],
        )
        db.add(period)
        db.flush()
        for task in spec["tasks"]:
            snap = next(snap_iter)
            life = _lifecycle_row_kwargs(
                db, report, task, snap,
                seen=seen_work_items,
                legacy_completed_dates=legacy_completed_dates,
                existing_links=existing_links,
            )
            _add_task_row(db, report, period.id, task, snap, life)


def _add_task_row(
    db: Session,
    report: DailyWorkReport,
    period_id: uuid.UUID | None,
    task,
    snap: dict,
    life: dict,
) -> None:
    """Insert one work_report_tasks row from its validated input + snapshots."""
    # The six unit columns. A lumpsum row that sent its Count as the explicit
    # count_field/count_value PAIR has that value written into the named
    # column here — the one place a count is ever redirected, and only ever to
    # the column the client itself named (already validated by _validate_tasks).
    # Every other row's counts are its own, unchanged.
    counts = {column: getattr(task, column) for column in COUNT_FIELD_BY_UNIT.values()}
    if snap["count_field"] is not None and snap["count_value"] is not None:
        counts[COUNT_FIELD_BY_UNIT[snap["count_field"]]] = snap["count_value"]
    db.add(
        WorkReportTask(
            report_id=report.id,
            period_id=period_id,
            project_id=task.project_id,
            description=task.description,
            minutes_spent=task.minutes_spent,
            task_minutes_spent=task.task_minutes_spent,
            activity_type=snap["activity_type"],
            **counts,
            sub_activity_id=task.sub_activity_id,
            sub_activity_name=snap["sub_activity_name"],
            activity_name=snap["activity_name"],
            # Already validated/cleared for static eligibility by _validate_tasks;
            # re-checked against the frozen target at submit.
            benchmark_exception_code=snap["benchmark_exception_code"],
            # The lumpsum row's employee-chosen count unit, already validated
            # (and cleared to None for every non-lumpsum row) by _validate_tasks.
            # Written at SAVE time — unlike the quantity modes, whose unit this
            # column takes from Activity Master at submit — so reopening a draft
            # restores the picked unit beside the Count it belongs to.
            relevant_count_field_snapshot=snap["count_field"],
            started_date=life["started_date"],
            due_date=life["due_date"],
            is_completed=life["is_completed"],
            completed_date=life["completed_date"],
            work_item_id=life["work_item_id"],
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


def _sync_legacy_full_day_period(
    db: Session, report: DailyWorkReport
) -> WorkReportPeriod:
    """Bring the single Full-Day period of a legacy (header+tasks) write in
    line with the header. Upserts the period; a report that was split_day and
    is edited through the legacy payload collapses back to one Full-Day period
    (the caller has already deleted the old task rows). Pre-period reports get
    their period created here on first edit."""
    period = db.execute(
        select(WorkReportPeriod).where(
            WorkReportPeriod.report_id == report.id,
            WorkReportPeriod.day_part == DayPart.full_day.value,
        )
    ).scalar_one_or_none()
    if period is None:
        _replace_periods(db, report)
        period = WorkReportPeriod(
            report_id=report.id, day_part=DayPart.full_day.value
        )
    fraction, legacy_half = _full_day_fraction(report.day_status)
    period.period_status = report.day_status
    period.location = report.location
    period.work_fraction = fraction
    period.is_legacy_half_day = legacy_half
    db.add(period)
    db.flush()
    report.report_mode = ReportMode.full_day.value
    return period


def _replace_periods(db: Session, report: DailyWorkReport) -> None:
    """Drop the report's period rows. Task rows must already be gone (deleting
    a period CASCADEs its tasks, so callers always clear tasks first to run the
    work-item reconciliation before anything cascades)."""
    db.execute(
        delete(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
    )
    db.flush()


def _attach_periods(db: Session, reports: list[DailyWorkReport]) -> None:
    """Attach each report's periods (with their — possibly Lead-trimmed — task
    rows) as a transient `.periods` attribute, and stamp `day_part` on every
    task row. Requires `.tasks` to be attached (and trimmed) first. A report
    with no period rows (written by pre-period code in the deploy gap) simply
    gets an empty list — readers fall back to the flat task list."""
    if not reports:
        return
    ids = [r.id for r in reports]
    rows = db.execute(
        select(WorkReportPeriod).where(WorkReportPeriod.report_id.in_(ids))
    ).scalars().all()
    by_report: dict[uuid.UUID, list[WorkReportPeriod]] = {r.id: [] for r in reports}
    part_by_period: dict[uuid.UUID, str] = {}
    for p in rows:
        by_report[p.report_id].append(p)
        part_by_period[p.id] = p.day_part
    for report in reports:
        periods = sorted(
            by_report[report.id], key=lambda p: _DAY_PART_ORDER.get(p.day_part, 9)
        )
        tasks_by_period: dict[uuid.UUID | None, list] = {}
        for t in getattr(report, "tasks", []):
            t.day_part = part_by_period.get(t.period_id)
            tasks_by_period.setdefault(t.period_id, []).append(t)
        for p in periods:
            p.tasks = tasks_by_period.get(p.id, [])
        report.periods = periods


def _assert_periods_submittable(db: Session, report: DailyWorkReport) -> None:
    """Every WORKING period must carry at least one activity row before the
    report can be submitted. (Non-working periods can never carry tasks — the
    write paths drop them.) Reports without period rows are covered by the
    legacy day-level check in submit_work_report."""
    periods = db.execute(
        select(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
    ).scalars().all()
    if not periods:
        return
    with_tasks = {
        pid for (pid,) in db.execute(
            select(WorkReportTask.period_id).where(
                WorkReportTask.report_id == report.id,
                WorkReportTask.period_id.is_not(None),
            ).distinct()
        ).all()
    }
    for p in periods:
        if _is_working_status(p.period_status) and p.id not in with_tasks:
            label = _DAY_PART_LABELS.get(p.day_part, p.day_part)
            raise AppError(
                "validation_error",
                f"Add at least one activity to the {label} period before submitting.",
                422,
            )


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

    # Normalize either payload shape (legacy full-day header+tasks, or the
    # explicit periods list) into period specs; leave-type periods carry no
    # task lines and are exempt from benchmark/overdue tracking. A working
    # day/period still requires at least one activity.
    norm = _normalize_periods(
        data.report_mode,
        data.periods,
        day_status=data.day_status,
        location=data.location,
        tasks=data.tasks,
    )
    all_tasks = [t for spec in norm["periods"] for t in spec["tasks"]]
    # Legacy parity: a period with NO status yet still owes activities (only an
    # explicit leave-type status exempts it), so None counts as task-requiring.
    requires_tasks = any(
        spec["period_status"] not in NO_ACTIVITY_DAY_STATUSES
        for spec in norm["periods"]
    )
    if requires_tasks and not all_tasks:
        raise AppError(
            "validation_error",
            "Add at least one activity, or choose a leave-type day status.",
            422,
        )
    total, snapshots = _validate_tasks(db, me.id, all_tasks)

    report = DailyWorkReport(
        employee_id=me.id,
        report_date=data.report_date,
        status=WorkReportStatus.draft,
        report_mode=norm["report_mode"].value,
        day_status=norm["day_status"],
        location=norm["location"],
        # Split-day remarks live on the periods; the header never mirrors them.
        remarks=None if norm["report_mode"] == ReportMode.split_day else data.remarks,
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
    seen_work_items: set = set()
    _insert_period_tasks(
        db, report, norm["periods"], snapshots, seen_work_items=seen_work_items
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
    # A submitted report is normally locked. The one exception: its author is
    # the *current* Project Head of one of its projects — they edit directly,
    # skipping the request-edit/grant-edit handshake. Same `reviewable` set as
    # the can_self_edit flag surfaced to the UI, so the two never disagree.
    head_self_edit = (
        report.status == WorkReportStatus.submitted
        and _report_in_projects(db, report.id, authz.reviewable_project_ids(db, actor))
    )
    if report.status not in _EDITABLE and not head_self_edit:
        raise AppError(
            "forbidden", "Only draft or rejected reports can be edited.", 403
        )

    fields = data.model_dump(exclude_unset=True)
    periods_update = "periods" in fields and data.periods is not None

    # Scalar header fields: update if explicitly provided. Applied BEFORE the
    # task/period rewrite so the synced period reads the new values; a periods
    # payload overwrites day_status/location again from its own derivation.
    _HEADER_FIELDS = (
        "summary", "day_status", "location", "remarks", "query_text",
        "well_head_no", "pm_plant", "task_list_count", "task_list_op_count",
        "maintenance_item_count", "maintenance_plan_count",
    )
    for field_name in _HEADER_FIELDS:
        if field_name in fields:
            setattr(report, field_name, getattr(data, field_name))

    # A leave-type day status (current or being set in this update) means the
    # report carries no project work: drop any task lines and zero the total,
    # regardless of what tasks the client sent.
    no_activity = report.day_status in NO_ACTIVITY_DAY_STATUSES

    if periods_update:
        # Periods payload (new clients): wholesale rewrite of the report's
        # periods + task rows, mirroring the legacy tasks-replace semantics.
        norm = _normalize_periods(
            data.report_mode,
            data.periods,
            day_status=None,
            location=None,
            tasks=None,
        )
        all_tasks = [t for spec in norm["periods"] for t in spec["tasks"]]
        # This report's own existing rows are about to be replaced, so they must
        # not count against the tag scope the new rows are checked against.
        total, snapshots = _validate_tasks(
            db, me.id, all_tasks, exclude_report_id=report.id
        )
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
        old_item_ids = wi.linked_item_ids_for_report(db, report.id)
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        _replace_periods(db, report)
        seen_work_items: set = set()
        _insert_period_tasks(
            db, report, norm["periods"], snapshots,
            seen_work_items=seen_work_items,
            legacy_completed_dates=old_completed_dates,
            existing_links=old_item_ids,
        )
        db.flush()
        removed = old_item_ids - wi.linked_item_ids_for_report(db, report.id)
        if removed:
            wi.reconcile_removed_links(
                db, report_date=report.report_date, removed_item_ids=removed
            )
        report.total_minutes = total
        report.report_mode = norm["report_mode"].value
        report.day_status = norm["day_status"]
        report.location = norm["location"]
        if norm["report_mode"] == ReportMode.split_day:
            # Split-day remarks live on the periods; the header never mirrors
            # them — clear any value this or an earlier save left behind.
            report.remarks = None
    elif no_activity:
        # Switching to a leave-type day drops the task lines; reconcile any work
        # items they linked (block beheading a started-here continued task).
        old_item_ids = wi.linked_item_ids_for_report(db, report.id)
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        if old_item_ids:
            wi.reconcile_removed_links(
                db, report_date=report.report_date, removed_item_ids=old_item_ids
            )
        report.total_minutes = 0
        # Legacy leave-type day: the report collapses to one (empty) Full-Day
        # period mirroring the header.
        _sync_legacy_full_day_period(db, report)
    elif "tasks" in fields and data.tasks is not None:
        total, snapshots = _validate_tasks(
            db, me.id, data.tasks, exclude_report_id=report.id
        )
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
        # Which work items this report linked BEFORE the row replace, so we can
        # detect continuations dropped by this edit and block/clean up safely.
        old_item_ids = wi.linked_item_ids_for_report(db, report.id)
        db.execute(delete(WorkReportTask).where(WorkReportTask.report_id == report.id))
        db.flush()
        # Legacy tasks payload is inherently full-day: upsert the Full-Day
        # period (collapsing a split report edited by a legacy client) and
        # link the replacement rows to it.
        period = _sync_legacy_full_day_period(db, report)
        seen_work_items: set = set()
        for task, snap in zip(data.tasks, snapshots):
            life = _lifecycle_row_kwargs(
                db, report, task, snap,
                seen=seen_work_items, legacy_completed_dates=old_completed_dates,
                existing_links=old_item_ids,
            )
            _add_task_row(db, report, period.id, task, snap, life)
        db.flush()
        # Work items no longer referenced by this report: block beheading a
        # started-here task that others continue, else drop the orphan.
        removed = old_item_ids - wi.linked_item_ids_for_report(db, report.id)
        if removed:
            wi.reconcile_removed_links(
                db, report_date=report.report_date, removed_item_ids=removed
            )
        report.total_minutes = total
    elif (
        ("day_status" in fields or "location" in fields)
        and report.report_mode == ReportMode.full_day.value
    ):
        # Header-only legacy edit of a full-day report: keep its single period
        # in step (period_status/location/fraction). A split report's periods
        # are only rewritten through the periods payload or a tasks replace.
        _sync_legacy_full_day_period(db, report)

    # Editing a reopened report (rejected / granted) returns it to draft and
    # clears the prior review. A Project Head editing their own submitted report
    # (head_self_edit) reopens it the same way — the edit lands as a draft they
    # then resubmit, so benchmarks recompute and no report is silently mutated
    # while still marked "submitted".
    if (
        report.status in (WorkReportStatus.rejected, WorkReportStatus.granted)
        or head_self_edit
    ):
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
    parent report's status. A legacy standalone task often completes days after
    its report is submitted, so that path still bypasses the locked-report edit
    restriction.

    Legacy (work_item_id NULL): touches is_completed/completed_date on this one
    row only, exactly as before.

    Work-item-linked: the WorkItem is authoritative and completion is per report.
    Completing stamps the item's completed_on = THIS row's report date and marks
    ONLY this row completed; sibling rows on other dates are left untouched (an
    earlier entry of a task finished today stays False). Completing is refused
    when the task is already completed on another report, when this report is not
    editable, or when a later continuation exists (which would backdate the
    overall completion). Reopening is allowed only on the report that completed
    the task and only while it is still editable. See work_items.py for the rules."""
    row = db.get(WorkReportTask, task_id)
    if row is None:
        raise AppError("not_found", "Task not found.", 404)
    report = db.get(DailyWorkReport, row.report_id)
    if report is None:
        raise AppError("not_found", "Task not found.", 404)
    _assert_author(db, actor, report)

    if row.work_item_id is not None:
        item = db.get(wi.WorkItem, row.work_item_id)
        if item is None:
            raise AppError("not_found", "Task not found.", 404)
        wi.complete_via_endpoint(
            db,
            item=item,
            is_completed=data.is_completed,
            report_date=report.report_date,
            report_editable=report.status in _EDITABLE,
        )
        db.flush()
        # Mirror ONLY this row from the item (row-level, per-report completion).
        m = wi.mirror_fields(item, report.report_date)
        row.is_completed = m["is_completed"]
        row.completed_date = m["completed_date"]
        db.add(row)
        db.commit()
    else:
        row.is_completed = data.is_completed
        row.completed_date = _today() if data.is_completed else None
        db.add(row)
        db.commit()

    # Re-decorate so the response carries the daily/overall completion fields.
    _attach_tasks(db, [report])
    return next(t for t in report.tasks if t.id == task_id)


# Single source of truth for unit -> column (app.modules.activity_master.models).
# Kept as a module-level alias so existing readers of this name still work.
_COUNT_FIELD_COLUMNS = COUNT_FIELD_BY_UNIT


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
    # Period-level scaling (migration 0060): each row's NUMERIC target is
    # base x its period's work_fraction (full day 1.0, half 0.5) — the frozen
    # benchmark_value_snapshot stays the EFFECTIVE target, with the base and
    # fraction recorded beside it. Rows without a period (pre-period code)
    # fall back to the legacy report-wide half_day rule, bit-identical to the
    # old behaviour.
    legacy_half = report.day_status == DayStatus.half_day
    fraction_by_period: dict[uuid.UUID, Decimal] = {
        p.id: Decimal(p.work_fraction)
        for p in db.execute(
            select(WorkReportPeriod).where(WorkReportPeriod.report_id == report.id)
        ).scalars()
    }
    rows = db.execute(
        select(WorkReportTask).where(WorkReportTask.report_id == report.id)
    ).scalars().all()
    for row in rows:
        sub = (
            db.get(ActivityMaster, row.sub_activity_id)
            if row.sub_activity_id is not None
            else None
        )
        if sub is None:
            # No benchmark to evaluate — and therefore nothing an exception
            # could except (a row whose sub-activity has since been removed).
            if row.benchmark_exception_code is not None:
                row.benchmark_exception_code = None
                db.add(row)
            continue
        fraction = fraction_by_period.get(row.period_id)
        if fraction is None:
            fraction = Decimal("0.5") if legacy_half else Decimal("1.0")
        base_value = sub.benchmark_value
        # Whole units only: half of a 35-tag benchmark is frozen as 18, not
        # 17.5 (see activity_master.service.scaled_target). The base and the
        # fraction are recorded beside it, so the derivation stays inspectable.
        benchmark_value = (
            scaled_target(base_value, fraction) if base_value is not None else None
        )
        row.benchmark_type_snapshot = sub.benchmark_type
        row.benchmark_value_snapshot = benchmark_value
        row.benchmark_base_value_snapshot = base_value
        row.benchmark_fraction_snapshot = fraction
        row.benchmark_period_days_snapshot = sub.benchmark_period_days
        # A LUMPSUM row's unit is the employee's own choice, already written at
        # save time (_add_task_row); the master has none to freeze, so rewriting
        # it here would silently drop the selection the moment the report was
        # submitted. Every other mode keeps the original behaviour exactly —
        # including a row whose sub-activity was RECONFIGURED into a quantity
        # mode, which stops being a lumpsum row and is overwritten as before.
        if not is_lumpsum_unit_row(sub.benchmark_type, sub.relevant_count_field):
            row.relevant_count_field_snapshot = sub.relevant_count_field
        actual_value = None
        if sub.relevant_count_field:
            column = _COUNT_FIELD_COLUMNS.get(sub.relevant_count_field)
            actual_value = getattr(row, column) if column else None
        # Authoritative exception verdict (migration 0063), taken here because
        # this is where the effective per-period target is frozen. An exception
        # that no longer holds — the actual reached or passed the target, the
        # target vanished, the sub-activity was reconfigured — is CLEARED, so a
        # stale 100% can never survive an edit-and-resubmit. deficit and
        # productivity_pct stay the REAL figures: the exception is an evaluation
        # rule for the benchmark report, not a rewrite of the row's own numbers.
        if row.benchmark_exception_code is not None and not is_valid_exception(
            row.benchmark_exception_code,
            benchmark_type=sub.benchmark_type,
            count_field=sub.relevant_count_field,
            target=benchmark_value,
            actual=actual_value,
        ):
            row.benchmark_exception_code = None
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
    # Split-day: every WORKING period needs its own activity row (a report
    # with only the first half filled in cannot be submitted).
    _assert_periods_submittable(db, report)

    # Re-check activity access at submit (migration 0061): a draft saved while an
    # activity was COMMON/granted must not be submitted after it was restricted /
    # the grant revoked. Existing task rows duck-type as the tasks the access
    # validator expects (sub_activity_id / work_item_id); an open work-item
    # continuation is still allowed by the exception inside the validator.
    submit_rows = db.execute(
        select(WorkReportTask).where(WorkReportTask.report_id == report.id)
    ).scalars().all()
    access_service.validate_report_activity_access(
        db, employee_id=report.employee_id, tasks=submit_rows
    )

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
    """Only the Project Head of one of the report's projects may grant edit
    access. The PM has no grant-edit rights, and a user can never grant edit on
    their own report."""
    me = _current_employee(db, actor)
    if me is None or report.employee_id == me.id:
        raise AppError("forbidden", "You are not permitted to review this report.", 403)
    if _report_in_projects(db, report.id, authz.reviewable_project_ids(db, actor)):
        return
    raise AppError("forbidden", "You are not permitted to review this report.", 403)


def request_edit_work_report(
    db: Session, actor: User, report_id: uuid.UUID, data: WorkReportEditRequest
) -> DailyWorkReport:
    """Author asks the Project Head to reopen a submitted (locked) report for
    editing, with a reason explaining why the edit is needed."""
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
    _notify_project_heads(
        db, decorated, author, "report_edit_requested",
        f"{author.full_name} requested to edit a report",
        f"{author.full_name} asked to edit their work report for "
        f"{report.report_date}. Reason: {data.note}",
    )
    return decorated


def grant_edit_work_report(
    db: Session, actor: User, report_id: uuid.UUID
) -> DailyWorkReport:
    """The Project Head grants an edit request — reopens the report so the
    author can edit and resubmit. Uses the editable 'granted' state."""
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
    # Deleting the report cascades its task rows. If those rows started a work
    # item that later reports still continue, block (can't behead the deadline);
    # otherwise clean up any now-orphaned work item. reconcile runs after the
    # cascade so reference counts are final; an AppError here rolls the whole
    # delete back (nothing is committed yet).
    linked = wi.linked_item_ids_for_report(db, report.id)
    report_date = report.report_date
    db.delete(report)
    db.flush()
    if linked:
        wi.reconcile_removed_links(
            db, report_date=report_date, removed_item_ids=linked
        )
    db.commit()
