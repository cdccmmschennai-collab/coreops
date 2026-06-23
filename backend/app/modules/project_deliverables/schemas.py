"""Pydantic schemas for project deliverables."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.project_deliverables.models import DeliverableStatus


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None  # populated by service (global list only)
    project_code: str | None = None  # populated by service (global list only)
    name: str
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    owner_name: str | None = None   # populated by service
    status: DeliverableStatus
    completion_date: date | None = None
    created_at: datetime
    updated_at: datetime


class DeliverableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    status: DeliverableStatus = DeliverableStatus.pending
    completion_date: date | None = None


class DeliverableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    status: DeliverableStatus | None = None
    completion_date: date | None = None
    # Mandatory when a tracked field (planned start date, due date, or a status
    # reversal from completed) changes; ignored otherwise.
    reason: str | None = Field(default=None, max_length=500)


class DeliverableChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deliverable_id: uuid.UUID
    field: str
    old_value: str | None = None
    new_value: str | None = None
    changed_by: uuid.UUID
    changed_by_name: str = ""   # populated by service join
    reason: str
    changed_at: datetime
