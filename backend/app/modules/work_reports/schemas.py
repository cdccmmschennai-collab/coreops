"""Daily Work Report pydantic schemas (mirrors attendance/projects).

Field-level validation lives here (lengths, minutes bounds, >=1 task). Cross-field
and business rules — future-date, edit window, duplicate (employee, date), project
membership/active, daily sum <= 1440, and workflow transitions — are enforced in the
service layer (and the DB constraints). total_minutes is derived server-side and is
read-only output; it is never accepted on create/update.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.work_reports.models import WorkReportStatus

# Bounds from DAILY_WORK_REPORTS_SPEC.md §6.
_SUMMARY_MAX = 2000
_DESCRIPTION_MAX = 2000
_REVIEW_NOTE_MAX = 1000
_MIN_TASK_MINUTES = 1
_MAX_DAY_MINUTES = 1440


class WorkReportTaskIn(BaseModel):
    project_id: uuid.UUID
    description: str = Field(min_length=1, max_length=_DESCRIPTION_MAX)
    minutes_spent: int = Field(ge=_MIN_TASK_MINUTES, le=_MAX_DAY_MINUTES)


class WorkReportTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    description: str
    minutes_spent: int


class WorkReportCreate(BaseModel):
    report_date: date
    summary: str | None = Field(default=None, max_length=_SUMMARY_MAX)
    tasks: list[WorkReportTaskIn] = Field(min_length=1)


class WorkReportUpdate(BaseModel):
    summary: str | None = Field(default=None, max_length=_SUMMARY_MAX)
    tasks: list[WorkReportTaskIn] | None = Field(default=None, min_length=1)


class WorkReportReject(BaseModel):
    review_note: str = Field(min_length=1, max_length=_REVIEW_NOTE_MAX)


class WorkReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    report_date: date
    status: WorkReportStatus
    summary: str | None = None
    total_minutes: int
    tasks: list[WorkReportTaskOut] = []
    submitted_at: datetime | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
    created_at: datetime


class WorkReportPage(BaseModel):
    items: list[WorkReportOut]
    total: int
    limit: int
    offset: int
