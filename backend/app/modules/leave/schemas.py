"""Leave Request pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.leave.classification import LeaveClassification
from app.modules.leave.models import LeaveStatus

_REASON_MAX = 2000
_COMMENT_MAX = 1000


class LeaveRequestCreate(BaseModel):
    # No leave type: the classification is not something the employee chooses,
    # it is what the dates cost. See `leave/classification.py`.
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class LeaveRequestUpdate(BaseModel):
    start_date: date | None = None
    end_date: date | None = None
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class LeaveReviewBody(BaseModel):
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX)


class LeaveRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str | None = None
    start_date: date
    end_date: date
    # How many days of [start_date, end_date] the office is actually open for -
    # the number the employee is charged, not the calendar span. Computed by
    # `service.attach_computed_fields` from `effects.leave_working_days`, so the
    # UI can never disagree with what an approval deducts. `start_date`/`end_date`
    # are untouched: they remain the range the employee asked for.
    working_days: int
    # Normal (<= 3 working days) or Special (> 3), derived from `working_days`
    # by `leave/classification.py`. Never stored, so it cannot go stale when a
    # request's dates change or a holiday lands inside its range.
    classification: LeaveClassification
    reason: str | None = None
    status: LeaveStatus
    manager_id: uuid.UUID | None = None
    manager_comment: str | None = None
    routed_project_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class LeaveClassificationPreviewOut(BaseModel):
    """What a range WOULD cost and be classified as, before anything is filed.

    Exists so the leave form can show the employee the classification their
    dates produce without guessing at it: the office week and the company
    calendar live on the server, and this asks the very same
    `leave_working_days` -> `classify_leave` pair the eventual request will be
    read through. The form never does calendar arithmetic of its own, so the
    frozen "Leave type" it displays cannot disagree with the saved request.
    """

    start_date: date
    end_date: date
    working_days: int
    classification: LeaveClassification


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


# ---------- attendance summary (cancellation-queue decision support) -------

class LeaveAttendanceSummaryOut(BaseModel):
    """What attendance already exists across one leave request's dates.

    Summary only — a single word the manager can read at a glance. CoreOps
    attendance is maintained by hand and cancellation never writes to it; this
    exists so the manager knows what they will need to review afterwards.
    """
    leave_request_id: uuid.UUID
    # present | leave | absent | mixed | none
    summary: str
    days_recorded: int


class AttendanceSummaryRequest(BaseModel):
    leave_request_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)


class AttendanceSummaryResponse(BaseModel):
    items: list[LeaveAttendanceSummaryOut]
