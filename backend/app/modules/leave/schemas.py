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


# ---------- deliverable impact (leave-review decision support) -------------

class DeliverableConflictOut(BaseModel):
    """One Planned deliverable whose target date falls within ±2 days of a
    leave request, on a project the requesting employee is assigned to."""
    deliverable_id: uuid.UUID
    deliverable_name: str            # the deliverable / activity name
    project_id: uuid.UUID
    project_name: str | None = None
    project_code: str | None = None
    status: str                      # always 'planned' for now
    target_date: date | None = None  # planned delivery date
    employee_id: uuid.UUID
    employee_name: str | None = None


class LeaveDeliverableImpactOut(BaseModel):
    leave_request_id: uuid.UUID
    conflicts: list[DeliverableConflictOut]


class DeliverableImpactRequest(BaseModel):
    leave_request_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class DeliverableImpactResponse(BaseModel):
    items: list[LeaveDeliverableImpactOut]
