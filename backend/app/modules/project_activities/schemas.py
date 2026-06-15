"""Project activity pydantic schemas."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityStatus = Literal["open", "in_progress", "closed"]


class ProjectActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    activity_type_id: uuid.UUID | None
    activity_type_name: str | None
    title: str
    status: str
    assigned_to_id: uuid.UUID | None
    assigned_to_name: str | None
    target_date: date | None
    closed_date: date | None
    remarks: str | None
    sort_order: int
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ProjectActivityCreate(BaseModel):
    activity_type_id: uuid.UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    status: ActivityStatus = "open"
    assigned_to_id: uuid.UUID | None = None
    target_date: date | None = None
    closed_date: date | None = None
    remarks: str | None = None
    sort_order: int = 0


class ProjectActivityUpdate(BaseModel):
    activity_type_id: uuid.UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=500)
    status: ActivityStatus | None = None
    assigned_to_id: uuid.UUID | None = None
    target_date: date | None = None
    closed_date: date | None = None
    remarks: str | None = None
    sort_order: int | None = None
