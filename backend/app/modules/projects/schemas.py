"""Project pydantic schemas."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.models import (
    ActivityMemberRole,
    ProjectMemberRole,
    ProjectStatus,
)

# Project scope classification. Mirrors the SCOPE_TYPE_* constants in models.py
# and the activity_master AccessType precedent (Literal over a stored VARCHAR,
# not a python Enum) — FastAPI renders it as a string enum in the OpenAPI
# contract, so an unknown value such as "RANDOM" is rejected with 422 before it
# can reach the database.
ProjectScopeType = Literal["NONE", "TAG_BASED"]

# How settled the estimated tag count is. NULL (absent) means no estimate has
# been established yet — deliberately not modelled as a NOT_STARTED value.
TagScopeStatus = Literal["PROVISIONAL", "BASELINED"]


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    # Nullable (migration 0078) — a project may have no permanent code yet.
    # See work_reports for the per-activity employee-entered fallback.
    code: str | None = None
    name: str
    job_code_id: uuid.UUID | None = None
    job_code_code: str | None = None   # populated by service join
    job_code_name: str | None = None   # populated by service join
    planning_plant_id: uuid.UUID | None = None
    maintenance_plant_id: uuid.UUID | None = None
    maintenance_plant_code: str | None = None          # populated by service join
    maintenance_plant_description: str | None = None   # populated by service join
    planning_plant_code: str | None = None              # populated by service join
    planning_plant_description: str | None = None       # populated by service join
    head_employee_id: uuid.UUID | None = None
    head_employee_name: str | None = None               # populated by service join
    client: str | None = None
    description: str | None = None
    status: ProjectStatus
    # Project Tag Scope classification. Always present; pre-0064 projects read
    # "NONE" from the column's backfill.
    scope_type: ProjectScopeType = "NONE"
    # Current tag scope. null count + null status + revision 0 = "not
    # established yet"; a NONE project stays in that state permanently.
    estimated_tag_count: int | None = None
    tag_scope_status: TagScopeStatus | None = None
    tag_scope_revision: int = 0
    tag_scope_updated_at: datetime | None = None
    tag_scope_updated_by: uuid.UUID | None = None
    start_date: date | None = None
    planned_completion_date: date | None = None
    actual_completion_date: date | None = None
    days_running: int | None = None   # populated by service (today - start_date)
    member_count: int = 0
    created_at: datetime


class ProjectCreate(BaseModel):
    # Nullable (migration 0078): a project may begin work before a permanent
    # code is assigned (e.g. a Tag Estimation engagement) — omit it, or send
    # null, to create one with none. A code that IS provided is still
    # validated/enforced unique exactly as before; this only removes the
    # requirement that one be provided at all.
    code: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    job_code: str | None = None   # free text; resolved to a JobCode by the service
    planning_plant_id: uuid.UUID | None = None   # project master link to a Planning Plant
    maintenance_plant_id: uuid.UUID | None = None
    client: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.planning
    # Optional: a client that predates this field (or an import) omits it and
    # gets a normal, non-tag project.
    scope_type: ProjectScopeType = "NONE"
    start_date: date | None = None
    planned_completion_date: date | None = None
    actual_completion_date: date | None = None


class ProjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    job_code: str | None = None   # free text; resolved to a JobCode by the service
    planning_plant_id: uuid.UUID | None = None   # project master link to a Planning Plant
    maintenance_plant_id: uuid.UUID | None = None
    client: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    # Omitted -> unchanged. Reclassifying is allowed in both directions in this
    # phase because no tag-scope records exist yet to be orphaned.
    scope_type: ProjectScopeType | None = None
    start_date: date | None = None
    actual_completion_date: date | None = None
    # Allowed only for initial set (when the project has no planned date yet).
    # Use PATCH /projects/{id}/planned-completion-date (with reason) for subsequent changes.
    planned_completion_date: date | None = None


class TagScopeRevisionOut(BaseModel):
    """One recorded scope change. Revision 1 carries null previous_* values."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    revision: int
    previous_estimated_tag_count: int | None
    new_estimated_tag_count: int
    previous_status: TagScopeStatus | None
    new_status: TagScopeStatus
    reason: str
    changed_by: uuid.UUID
    changed_by_name: str = ""   # populated by service join
    created_at: datetime


class TagScopeUpdate(BaseModel):
    """PUT /projects/{id}/tag-scope — establish or revise the estimated scope.

    The client supplies only what a human decided: how many tags, how settled
    the number is, and why it changed. Everything else on the revision row
    (revision number, previous_*, changed_by, created_at) is derived server-side
    — see ``service.record_tag_scope_revision``.
    """

    # gt=0 rejects 0 and negatives before the service runs; pydantic also
    # rejects "abc", 2.5 and a missing value with a 422. The same rule is
    # re-checked in the service and again by the projects_* CHECK constraints.
    estimated_tag_count: int = Field(gt=0)
    status: TagScopeStatus
    # Optional only for the very first estimate, where the service substitutes
    # "Initial project estimate". Revising an existing scope requires a real,
    # non-whitespace reason (422 otherwise).
    reason: str | None = Field(default=None, max_length=500)
    # Optimistic concurrency: the tag_scope_revision the client was looking at
    # when it opened the form (0 for a project with no scope yet). If the stored
    # revision has moved on, the update is refused with 409 rather than silently
    # superseding the other person's revision.
    expected_revision: int = Field(ge=0)


class TagScopeOut(BaseModel):
    """GET/PUT /projects/{id}/tag-scope — current scope plus its full history.

    Carries no progress, no worked-tag count and no remaining figure; those
    belong to the later progress phase.
    """

    project_id: uuid.UUID
    scope_type: ProjectScopeType
    estimated_tag_count: int | None = None
    tag_scope_status: TagScopeStatus | None = None
    tag_scope_revision: int = 0
    tag_scope_updated_at: datetime | None = None
    tag_scope_updated_by: uuid.UUID | None = None
    tag_scope_updated_by_name: str | None = None   # populated by service join
    revisions: list[TagScopeRevisionOut] = Field(default_factory=list)


class TagScopeProgressRow(BaseModel):
    """One tag-counted sub-activity's progress against the project's scope.

    Every row carries the SAME estimated_tag_count: activities progress against
    the project's tag universe independently, so the rows are not shares of a
    pool and are not expected to sum to it.

    Activity and Sub-Activity are separate fields, joined through
    activity_master.parent_id — never one combined label, and never derived by
    splitting the sub-activity's name. activity_* is nullable only for the
    data-integrity case of a sub-activity with no parent row; the UI shows a
    placeholder there rather than hiding the progress.

    reported_tags / remaining_tags are whole tags and always present. A client
    renders remaining_tags directly: it is never null, never negative, and needs
    no arithmetic on the client to produce.
    """

    activity_id: uuid.UUID | None = None
    activity_name: str | None = None
    sub_activity_id: uuid.UUID
    sub_activity_name: str
    reported_tags: int
    estimated_tag_count: int
    remaining_tags: int


class ProjectSummaryOut(BaseModel):
    """GET /projects/{id}/summary — what the Summary tab renders.

    `tag_progress` is empty for a normal project, and for a tag-based project
    with no estimate established yet: there is no capacity to measure against,
    and inventing "0 / 0" would be a wrong summary rather than an empty one.
    """

    project_id: uuid.UUID
    scope_type: ProjectScopeType
    estimated_tag_count: int | None = None
    tag_scope_status: TagScopeStatus | None = None
    tag_progress: list[TagScopeProgressRow] = Field(default_factory=list)


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
    limit: int
    offset: int


class ProjectMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    role: ProjectMemberRole
    created_at: datetime


class ProjectMemberCreate(BaseModel):
    employee_id: uuid.UUID
    role: ProjectMemberRole = ProjectMemberRole.contributor


class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectMemberRole


class ActivityMemberOut(BaseModel):
    """One person's staffing on one project activity."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    activity_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str = ""   # populated by service join
    role: ActivityMemberRole
    is_qc: bool
    created_at: datetime


class ActivityMemberCreate(BaseModel):
    employee_id: uuid.UUID
    role: ActivityMemberRole
    is_qc: bool = False


class ActivityMemberUpdate(BaseModel):
    # Both optional: change the base role and/or toggle QC. Omitted fields are
    # left unchanged (promotion to lead is Head-only, enforced in the service).
    role: ActivityMemberRole | None = None
    is_qc: bool | None = None


class ActivityStaffingOut(BaseModel):
    """One project activity with its resolved staffing (Lead, the Contributor
    list, and which members hold QC). Named distinctly from the unrelated
    project_activities.ProjectActivityOut (the planning work-item feature)."""
    activity_id: uuid.UUID
    activity_code: str | None = None   # populated by service join (activity_master.code)
    activity_name: str = ""   # populated by service join (activity_master.name)
    lead: ActivityMemberOut | None = None
    contributors: list[ActivityMemberOut] = Field(default_factory=list)
    qc: list[ActivityMemberOut] = Field(default_factory=list)
    member_count: int = 0


class ProjectHeadUpdate(BaseModel):
    # null clears the Head; otherwise the employee assigned as project Head.
    head_employee_id: uuid.UUID | None = None


class LedProjectMember(BaseModel):
    employee_id: uuid.UUID
    name: str


class LedProject(BaseModel):
    project_id: uuid.UUID
    name: str
    # Nullable (migration 0078) — a project may have no permanent code yet.
    code: str | None = None
    members: list[LedProjectMember]


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    details: dict
    created_at: datetime


class PlannedDateUpdate(BaseModel):
    new_date: date | None = None
    reason: str = Field(min_length=1, max_length=500)


# ---------- Weekly Report (Phase 7) ----------------------------------------
# The two selectable cycles. A Literal (not free text) so an unsupported value
# is rejected with 422 by FastAPI before it reaches the service, and so the
# OpenAPI contract states the two options for the client.
WeeklyReportCycle = Literal["current", "previous"]

# Project allocation of the reported day. Deliberately NOT called Day Status:
# that is the attendance-shaped taxonomy (Leave / Week Off / Company Holiday /
# Work at Office...) and answers a different question.
WorkPeriod = Literal["full_day", "first_half", "second_half", "legacy_half_day"]


class WeeklyReportPeriodOut(BaseModel):
    """The resolved Friday-Thursday cycle the rows belong to. Always echoed back
    so the Head never has to guess what "Current Week" meant."""

    type: WeeklyReportCycle
    start_date: date
    end_date: date


class WeeklyReportRow(BaseModel):
    """One reported activity line: employee + date + work period + activity.

    Null is meaningful throughout and is never coerced to 0 or "": a null count
    means that unit does not apply to this row, a null benchmark means the
    activity has no target, and a null task_status means the row is not
    task-mode work. The clients render those as "-", which is not the same
    statement as a zero.
    """

    report_date: date
    work_period: WorkPeriod
    work_period_label: str
    employee_name: str
    # PROJECT CODE ONLY (e.g. "4716-LC25102900") — never the project name, in
    # the preview or the export. Nullable (migration 0078): a project with no
    # permanent code yet.
    project_code: str | None = None
    activity_name: str | None = None
    sub_activity_name: str | None = None
    # Numeric target frozen at submit time, or the textual label for a
    # completion-only task ("Lump Sum"). Both null = no benchmark configured.
    benchmark: float | None = None
    benchmark_label: str | None = None
    # The six recorded units. Present when the row carries the value or the
    # benchmark measures that unit; null when the unit does not apply.
    tags: int | None = None
    docs: int | None = None
    bom: int | None = None
    spares: int | None = None
    pages: int | None = None
    records: int | None = None
    # Derived task lifecycle (IN_PROGRESS / DUE_TODAY / OVERDUE /
    # COMPLETED_ON_TIME / COMPLETED_LATE) for task-mode rows only.
    task_status: str | None = None
    task_status_label: str | None = None
    # The note belonging to this row: its own activity remark
    # (work_report_tasks.description) when present, else its own period's remark
    # (a half's own note; the report header's note for a Full Day). Never the
    # Query / Issues field.
    remarks: str | None = None


class WeeklyReportOut(BaseModel):
    project_id: uuid.UUID
    project_code: str | None = None
    period: WeeklyReportPeriodOut
    rows: list[WeeklyReportRow] = Field(default_factory=list)
    row_count: int = 0


class PlannedDateChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    old_date: date | None
    new_date: date | None
    changed_by: uuid.UUID
    changed_by_name: str = ""   # populated by service join
    reason: str
    changed_at: datetime
