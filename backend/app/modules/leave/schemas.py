"""Leave Request pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.leave.models import LeaveStatus, LeaveType

_REASON_MAX = 2000
_COMMENT_MAX = 1000


class LeaveRequestCreate(BaseModel):
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class LeaveRequestUpdate(BaseModel):
    leave_type: LeaveType | None = None
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class LeaveReviewBody(BaseModel):
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX)


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    leave_type: LeaveType
    start_date: date
    end_date: date
    reason: str | None = None
    status: LeaveStatus
    manager_id: uuid.UUID | None = None
    manager_comment: str | None = None
    created_at: datetime
    updated_at: datetime


class LeaveRequestPage(BaseModel):
    items: list[LeaveRequestOut]
    total: int
    limit: int
    offset: int
