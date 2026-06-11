"""Daily Work Report pydantic schemas.

Extended in migration 0006 with Google Form fields (day_status, location,
remarks, query_text, counts, well_head_no, pm_plant) and optional minutes_spent.

Field-level validation lives here. Cross-field and business rules are enforced
in the service layer. total_minutes is derived server-side and never accepted
from the client.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.work_reports.models import DayStatus, WorkLocation, WorkReportStatus

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
    # minutes_spent is optional — Google Form has no time field
    minutes_spent: int | None = Field(default=None, ge=0, le=_MAX_DAY_MINUTES)
    activity_type: str | None = Field(default=None, max_length=200)
    tags_count: int = Field(default=0, ge=0)
    docs_count: int = Field(default=0, ge=0)
    bom_count: int = Field(default=0, ge=0)
    spares_count: int = Field(default=0, ge=0)


class WorkReportTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    # Snapshot fields (populated at save time; null for records predating migration 0017).
    project_name: str | None = None
    project_code: str | None = None
    project_job_code_code: str | None = None
    description: str
    minutes_spent: int | None = None
    activity_type: str | None = None
    tags_count: int = 0
    docs_count: int = 0
    bom_count: int = 0
    spares_count: int = 0


class WorkReportCreate(BaseModel):
    report_date: date
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
    tasks: list[WorkReportTaskIn] = Field(min_length=1)


class WorkReportUpdate(BaseModel):
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
    tasks: list[WorkReportTaskIn] | None = Field(default=None, min_length=1)


class WorkReportReject(BaseModel):
    review_note: str = Field(min_length=1, max_length=_REVIEW_NOTE_MAX)


class WorkReportEditRequest(BaseModel):
    # Author's reason for requesting edit access on a submitted report.
    note: str = Field(min_length=1, max_length=_REVIEW_NOTE_MAX)


class WorkReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    report_date: date
    status: WorkReportStatus
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
    # Per-actor: True when the current user may reject / grant edit on this report
    # (PM for any report; team lead for reports on their projects). Set in service.
    can_review: bool = False
    created_at: datetime


class WorkReportPage(BaseModel):
    items: list[WorkReportOut]
    total: int
    limit: int
    offset: int
