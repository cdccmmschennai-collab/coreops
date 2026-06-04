"""ActivityType pydantic schemas."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ActivityCategory = Literal["GENERAL", "PROJECT", "TAG_ESTIMATION"]


class ActivityTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str | None
    name: str
    category: str
    requires_project: bool
    is_active: bool
    created_at: datetime


class ActivityTypeCreate(BaseModel):
    code: str | None = Field(default=None, min_length=1, max_length=10)
    name: str = Field(min_length=1, max_length=200)
    category: ActivityCategory = "GENERAL"
    requires_project: bool = False
    is_active: bool = True


class ActivityTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: ActivityCategory | None = None
    requires_project: bool | None = None
    is_active: bool | None = None


class ActivityTypePage(BaseModel):
    items: list[ActivityTypeOut]
    total: int
    limit: int
    offset: int
