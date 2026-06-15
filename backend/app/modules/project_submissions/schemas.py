"""Project submission pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_submissions.models import SubmissionStatus


class SubmissionItemIn(BaseModel):
    activity_type_id: uuid.UUID | None = None
    activity_label: str = Field(min_length=1)
    quantity: int = Field(gt=0)
    unit: str = Field(min_length=1)


class SubmissionItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    activity_type_id: uuid.UUID | None
    activity_label: str
    quantity: int
    unit: str


class SubmissionCreate(BaseModel):
    submission_date: date
    period_start: date
    period_end: date
    notes: str | None = None
    items: list[SubmissionItemIn] = Field(default_factory=list)


class SubmissionUpdate(BaseModel):
    submission_date: date | None = None
    period_start: date | None = None
    period_end: date | None = None
    notes: str | None = None
    items: list[SubmissionItemIn] | None = None


class SubmissionStatusUpdate(BaseModel):
    status: SubmissionStatus
    review_note: str | None = None


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    submission_date: date
    period_start: date
    period_end: date
    status: SubmissionStatus
    notes: str | None
    submitted_by: uuid.UUID
    submitted_by_name: str = ""
    reviewed_by: uuid.UUID | None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None
    review_note: str | None
    items: list[SubmissionItemOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
