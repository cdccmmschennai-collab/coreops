"""Office pydantic schemas."""
import uuid
from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class OfficeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    timezone: str
    shift_start: time
    shift_end: time
    break_minutes: int
    is_active: bool
    created_at: datetime


class OfficeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=100)
    shift_start: time
    shift_end: time
    break_minutes: int = Field(default=0, ge=0, le=480)
    is_active: bool = True


class OfficeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    shift_start: time | None = None
    shift_end: time | None = None
    break_minutes: int | None = Field(default=None, ge=0, le=480)
    is_active: bool | None = None


class OfficePage(BaseModel):
    items: list[OfficeOut]
    total: int
    limit: int
    offset: int
