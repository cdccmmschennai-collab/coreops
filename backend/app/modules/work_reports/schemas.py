"""Daily Work Report pydantic schemas.

Extended in migration 0006 with Google Form fields (day_status, location,
remarks, query_text, counts, well_head_no, pm_plant) and optional minutes_spent.

Field-level validation lives here. Cross-field and business rules are enforced
in the service layer. total_minutes is derived server-side and never accepted
from the client.
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.work_reports.models import (
    DayPart,
    DayStatus,
    ReportMode,
    WorkLocation,
    WorkReportStatus,
)


class WorkReportStatusFilter(str, enum.Enum):
    """Status values accepted by the report LIST filter.

    Mirrors WorkReportStatus but adds the **virtual** ``requested`` value: a
    ``submitted`` report that carries a pending edit request
    (``edit_requested_at IS NOT NULL``). No such status is persisted — the
    service translates the filter into a compound WHERE clause so pagination and
    counts stay correct. To keep the two mutually exclusive, the ``submitted``
    filter here means submitted *without* a pending edit request.
    """

    draft = "draft"
    submitted = "submitted"
    approved = "approved"
    rejected = "rejected"
    granted = "granted"
    requested = "requested"

_SUMMARY_MAX = 2000
_REMARKS_MAX = 2000
_QUERY_MAX = 2000
_DESCRIPTION_MAX = 2000
_REVIEW_NOTE_MAX = 1000
_MAX_DAY_MINUTES = 1440


class WorkReportTaskIn(BaseModel):
    project_id: uuid.UUID
    # Day remarks — optional free text (the daily report has no mandatory note)
    description: str = Field(default="", max_length=_DESCRIPTION_MAX)
    # minutes_spent = project-activity hours; task_minutes_spent = task hours.
    minutes_spent: int | None = Field(default=None, ge=0, le=_MAX_DAY_MINUTES)
    task_minutes_spent: int | None = Field(default=None, ge=0, le=_MAX_DAY_MINUTES)
    activity_type: str | None = Field(default=None, max_length=200)
    tags_count: int = Field(default=0, ge=0)
    docs_count: int = Field(default=0, ge=0)
    bom_count: int = Field(default=0, ge=0)
    spares_count: int = Field(default=0, ge=0)
    pages_count: int = Field(default=0, ge=0)
    records_count: int = Field(default=0, ge=0)
    # Activity Master selection — replaces free-text activity_type going forward.
    # QUANTITY sub-activities are benchmarked against whichever of the six count
    # fields above the master's relevant_count_field names — there is no separate
    # actual-count input.
    sub_activity_id: uuid.UUID | None = None
    # TASK sub-activities only: the completion checkbox. started_date/
    # due_date/completed_date are never client-supplied — see service.py.
    # This flag means "the whole task is finished", NOT "today's work is done":
    # it is never inferred from a count above, so entering pages_count=500 on a
    # TASK_WITH_QUANTITY row leaves the task open and carrying forward.
    is_completed: bool = False
    # Task continuation (feature-flagged). When set, this row continues an
    # existing WorkItem instead of starting a new one; the server validates
    # ownership/project/sub-activity/date and keeps the item's frozen deadline.
    # Ignored when TASK_CONTINUATION_ENABLED is off. NULL = start a new task.
    work_item_id: uuid.UUID | None = None
    # Independent of the project's own assigned plant — which plant the
    # employee actually worked at that day. Planning Plant code/description
    # auto-derive server-side; never client-supplied.
    maintenance_plant_id: uuid.UUID | None = None


class WorkReportTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    # Reporting-period link (migration 0060). day_part is resolved by the
    # service for display ("full_day" / "first_half" / "second_half"); both are
    # None only for rows written by pre-period code.
    period_id: uuid.UUID | None = None
    day_part: str | None = None
    # Snapshot fields (populated at save time; null for records predating migration 0017).
    project_name: str | None = None
    project_code: str | None = None
    project_job_code_code: str | None = None
    description: str
    minutes_spent: int | None = None
    task_minutes_spent: int | None = None
    activity_type: str | None = None
    tags_count: int = 0
    docs_count: int = 0
    bom_count: int = 0
    spares_count: int = 0
    pages_count: int = 0
    records_count: int = 0
    # Activity Master (snapshots frozen at save time; null for rows predating
    # this feature, or rows whose sub-activity carries no benchmark).
    sub_activity_id: uuid.UUID | None = None
    sub_activity_name: str | None = None
    activity_name: str | None = None
    # Frozen at submit time — see work_reports/service.py `_apply_benchmarks`.
    # benchmark_value_snapshot is the EFFECTIVE target (base x period fraction);
    # base/fraction record the derivation (migration 0060).
    benchmark_value_snapshot: Decimal | None = None
    benchmark_base_value_snapshot: Decimal | None = None
    benchmark_fraction_snapshot: Decimal | None = None
    benchmark_period_days_snapshot: int | None = None
    benchmark_type_snapshot: str | None = None
    # Which count field (tags/docs/bom/spares/pages/records) fed the calc above.
    # Historical rows legitimately still read 'docs' etc.; never rewritten on read.
    relevant_count_field_snapshot: str | None = None
    deficit: Decimal | None = None
    productivity_pct: Decimal | None = None
    # TASK_BASED tracking: started_date/due_date are computed server-side the
    # moment a TASK_BASED sub-activity is attached (see _validate_tasks);
    # is_completed/completed_date are set via the completion-toggle endpoint.
    started_date: date | None = None
    due_date: date | None = None
    is_completed: bool = False
    completed_date: date | None = None
    # Computed fresh on every read (never stored) — see
    # activity_master.service.compute_overdue. For a work-item-linked row these
    # mirror the authoritative WorkItem (see work_items.mirror_fields).
    is_overdue: bool = False
    days_overdue: int = 0
    # Task continuation (feature-flagged). work_item_id links this daily entry to
    # a persistent WorkItem; work_item_lifecycle is the derived state
    # (IN_PROGRESS/DUE_TODAY/OVERDUE/COMPLETED_ON_TIME/COMPLETED_LATE), computed
    # fresh on read. Both null for legacy standalone rows.
    work_item_id: uuid.UUID | None = None
    work_item_lifecycle: str | None = None
    # Explicit daily-row vs overall-task completion (task continuation), so the
    # UI never has to overload is_completed/completed_date (which are row-level).
    #   row_*            — completion state of THIS report row.
    #   overall_*        — the authoritative WorkItem completion + derived state.
    #   completed_on_this_report — True only when this report is where the overall
    #                      task was completed (row.is_completed AND
    #                      report_date == work_item.completed_on).
    #   completion_report_id — the report where completion happened (may be a
    #                      later report than this one).
    #   can_complete_here — server verdict on whether the completion control
    #                      should be active on THIS row (open task, editable
    #                      report, latest linked entry, not completed elsewhere).
    #                      Null for legacy non-work-item rows.
    row_is_completed: bool = False
    row_completed_date: date | None = None
    overall_completed_on: date | None = None
    overall_lifecycle: str | None = None
    completed_on_this_report: bool = False
    completion_report_id: uuid.UUID | None = None
    can_complete_here: bool | None = None
    # Maintenance Plant the employee worked at, frozen at save time (see
    # work_reports/service.py `_validate_tasks`). Independent of the
    # project's own assigned plant.
    maintenance_plant_id: uuid.UUID | None = None
    maintenance_plant_code: str | None = None
    maintenance_plant_description: str | None = None
    planning_plant_code: str | None = None
    planning_plant_description: str | None = None


class WorkReportPeriodIn(BaseModel):
    """One reporting period of a split-day (or explicit full-day) payload.

    There is deliberately NO work_fraction field: fractions are server-derived
    from day_part (full_day 1.0, halves 0.5) and can never be client-supplied.
    """

    day_part: DayPart
    period_status: DayStatus
    location: WorkLocation | None = None
    remarks: str | None = Field(default=None, max_length=_REMARKS_MAX)
    # Empty for a non-working period; a working period needs >= 1 activity
    # before the report can be SUBMITTED (drafts may be sparse, as today).
    tasks: list[WorkReportTaskIn] = Field(default_factory=list)


class WorkReportPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    day_part: str
    period_status: DayStatus | None = None
    location: WorkLocation | None = None
    remarks: str | None = None
    work_fraction: Decimal
    # Backfilled from a historical half_day report: rendered as a legacy
    # Full-Day period whose worked half is unknown (fraction 0.5).
    is_legacy_half_day: bool = False
    tasks: list[WorkReportTaskOut] = []


class WorkReportCreate(BaseModel):
    report_date: date
    # Split-day (migration 0060). Omitted / None = legacy full-day payload —
    # the service builds one Full-Day period from the header fields + `tasks`.
    # report_mode='split_day' (with `periods`) requires REPORT_DAY_PARTS_ENABLED.
    report_mode: ReportMode | None = None
    periods: list[WorkReportPeriodIn] | None = None
    # Google Form fields
    day_status: DayStatus | None = None
    location: WorkLocation | None = None
    remarks: str | None = Field(default=None, max_length=_REMARKS_MAX)
    query_text: str | None = Field(default=None, max_length=_QUERY_MAX)
    well_head_no: str | None = Field(default=None, max_length=500)
    pm_plant: str | None = Field(default=None, max_length=500)
    task_list_count: int | None = Field(default=None, ge=0)
    task_list_op_count: int | None = Field(default=None, ge=0)
    maintenance_item_count: int | None = Field(default=None, ge=0)
    maintenance_plan_count: int | None = Field(default=None, ge=0)
    # Legacy field kept for backward compat; new UI sends remarks instead
    summary: str | None = Field(default=None, max_length=_SUMMARY_MAX)
    # May be empty for leave-type day statuses (week off / leave / company
    # holiday / comp-off); the service requires ≥1 activity for working days.
    tasks: list[WorkReportTaskIn] = Field(default_factory=list)


class WorkReportUpdate(BaseModel):
    # Same convention as WorkReportCreate: None = "not part of this update"
    # (legacy header/tasks update); supplying periods rewrites the report's
    # periods + tasks wholesale, mirroring the existing tasks semantics.
    report_mode: ReportMode | None = None
    periods: list[WorkReportPeriodIn] | None = None
    day_status: DayStatus | None = None
    location: WorkLocation | None = None
    remarks: str | None = Field(default=None, max_length=_REMARKS_MAX)
    query_text: str | None = Field(default=None, max_length=_QUERY_MAX)
    well_head_no: str | None = Field(default=None, max_length=500)
    pm_plant: str | None = Field(default=None, max_length=500)
    task_list_count: int | None = Field(default=None, ge=0)
    task_list_op_count: int | None = Field(default=None, ge=0)
    maintenance_item_count: int | None = Field(default=None, ge=0)
    maintenance_plan_count: int | None = Field(default=None, ge=0)
    summary: str | None = Field(default=None, max_length=_SUMMARY_MAX)
    # None = "tasks not part of this update"; an empty list is allowed for
    # leave-type day statuses (the service clears any existing activity lines).
    tasks: list[WorkReportTaskIn] | None = None


class WorkReportEditRequest(BaseModel):
    # Author's reason for requesting edit access on a submitted report.
    note: str = Field(min_length=1, max_length=_REVIEW_NOTE_MAX)


class TaskCompletionUpdate(BaseModel):
    """Body for PATCH /work-reports/tasks/{task_id}/completion — the *only*
    way a TASK_BASED row's completion is changed once the parent report is
    submitted/locked, since these activities often complete days after the
    report they were logged on. Independent of report.status by design."""

    is_completed: bool


class WorkReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    report_date: date
    status: WorkReportStatus
    # Full-Day vs Split-Day (migration 0060). `periods` carries each period's
    # metadata + its own task rows; the flat `tasks` list below is preserved
    # unchanged for existing clients (every period task also appears there).
    report_mode: str = "full_day"
    periods: list[WorkReportPeriodOut] = []
    # Google Form fields
    day_status: DayStatus | None = None
    location: WorkLocation | None = None
    remarks: str | None = None
    query_text: str | None = None
    well_head_no: str | None = None
    pm_plant: str | None = None
    task_list_count: int | None = None
    task_list_op_count: int | None = None
    maintenance_item_count: int | None = None
    maintenance_plan_count: int | None = None
    # Legacy
    summary: str | None = None
    total_minutes: int
    tasks: list[WorkReportTaskOut] = []
    submitted_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    edit_requested_at: datetime | None = None
    edit_request_note: str | None = None
    # Per-actor: True when the current user may grant edit access on this report
    # — the Project Head of one of the report's projects. Set in service.
    can_review: bool = False
    # Per-actor: True when the current user is the author AND the current Project
    # Head of one of this (submitted) report's projects, so they may edit it
    # directly instead of requesting edit access. Set in service.
    can_self_edit: bool = False
    # Per-actor: True when this (another employee's) report is visible only
    # through the viewer's Activity-Lead assignments, so `tasks` was trimmed to
    # just the led activities' rows — a partial view of a mixed report. Set in
    # service (_restrict_to_led_rows); always False for PM/Head/own reports.
    scoped_to_led_activities: bool = False
    created_at: datetime


class WorkReportPage(BaseModel):
    items: list[WorkReportOut]
    total: int
    limit: int
    offset: int


class ReportScopeMember(BaseModel):
    """One active member of a scope project — the employee-filter option."""

    employee_id: uuid.UUID
    employee_code: str
    name: str


class ReportScopeActivity(BaseModel):
    activity_id: uuid.UUID
    name: str | None = None


class ReportScopeProject(BaseModel):
    """One project the caller can see foreign reports from. access='head'
    means the whole project (activities is empty = all); access='lead' means
    only the listed led activities."""

    project_id: uuid.UUID
    code: str
    name: str
    access: Literal["head", "lead"]
    activities: list[ReportScopeActivity] = []
    members: list[ReportScopeMember] = []


class ReportScopeOut(BaseModel):
    """GET /work-reports/scope — filter metadata for the reports view. Purely
    informational: the list/detail/export endpoints enforce the same scope
    server-side regardless of supplied query parameters."""

    is_project_head: bool = False
    is_activity_lead: bool = False
    projects: list[ReportScopeProject] = []


class OpenTaskOut(BaseModel):
    """One unfinished WorkItem the current employee can continue in a report,
    evaluated relative to that report's date. Backs GET /work-reports/open-tasks.
    Carries everything the form needs to prefill a continuation row."""

    work_item_id: uuid.UUID
    project_id: uuid.UUID
    project_code: str | None = None
    project_name: str | None = None
    activity_id: uuid.UUID | None = None
    activity_name: str | None = None
    sub_activity_id: uuid.UUID
    sub_activity_name: str | None = None
    started_on: date
    due_date: date
    target_days: int
    # IN_PROGRESS / DUE_TODAY / OVERDUE (completed items are never returned).
    lifecycle: str
    days_overdue: int = 0


class OpenTasksOut(BaseModel):
    items: list[OpenTaskOut] = []
