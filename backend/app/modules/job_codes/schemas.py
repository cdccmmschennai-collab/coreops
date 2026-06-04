"""JobCode pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class JobCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime


class JobCodeCreate(BaseModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    is_active: bool = True


class JobCodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    is_active: bool | None = None


class JobCodePage(BaseModel):
    items: list[JobCodeOut]
    total: int
    limit: int
    offset: int
