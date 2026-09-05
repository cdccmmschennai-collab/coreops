"""Leave Request pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.leave.classification import LeaveClassification
from app.modules.leave.models import LeaveHalfDayPeriod, LeaveStatus

_REASON_MAX = 2000
_COMMENT_MAX = 1000

# Worded with the two labels the Leave Request dropdown actually offers, so a
# reader is told to pick something they can see on screen.
_HALF_DAY_NEEDS_A_HALF = (
    "Choose which half of the day the leave covers - Half Day (First) or "
    "Half Day (Second)."
)

_HALF_DAY_IS_ONE_DAY = (
    "A half-day leave covers one day - set From and To to the same date, or "
    "file a full-day leave for the range."
)


class LeaveRequestCreate(BaseModel):
    # No leave type: the classification is not something the employee chooses,
    # it is what the dates cost. See `leave/classification.py`.
    start_date: date
    end_date: date
    reason: str | None = Field(default=None, max_length=_REASON_MAX)
    # HALF-DAY LEAVE (migration 0084). `half_day_period` is the stored fact: a
    # value means half a day, its absence means the whole of it - so a request
    # that says nothing about halves is exactly the full-day request it has
    # always been, and every existing caller keeps working unchanged.
    #
    # `half_day` exists ONLY to make an INCOMPLETE request refusable. A caller
    # that declares the leave is half a day without naming which half has not
    # made a valid request - the two halves are not interchangeable and picking
    # one for the requester would invent a decision they did not make. Naming a
    # half IS declaring a half day, so a caller that has already chosen never
    # has to send this flag; it only ever adds a refusal.
    half_day: bool = False
    half_day_period: LeaveHalfDayPeriod | None = None

    @model_validator(mode="after")
    def _half_day_is_complete_and_one_day(self) -> "LeaveRequestCreate":
        """The two rules a half-day request must satisfy, both pure.

        Checked here rather than in the service because neither needs a database
        or an employee: they are properties of the submitted body alone, and
        keeping them in the schema means the API answers 422 with a readable
        message before any row is read.

        The single-day rule is the API's half of the `leave_half_day_is_one_day`
        check constraint. Half a day is half of ONE day; a "half day" spanning a
        range would owe half a day to each of its working days, and both
        variants are defined to consume exactly one half day.
        """
        if self.half_day and self.half_day_period is None:
            raise ValueError(_HALF_DAY_NEEDS_A_HALF)
        if self.half_day_period is not None and self.start_date != self.end_date:
            raise ValueError(_HALF_DAY_IS_ONE_DAY)
        return self


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
    # Which half of the day this leave covers, or None for a full-day leave
    # (migration 0084). The Type a reader sees is composed from this and
    # `classification` together - a half-day request shows its variant's label,
    # every other request shows Normal or Special exactly as before.
    half_day_period: LeaveHalfDayPeriod | None = None
    reason: str | None = None
    status: LeaveStatus
    manager_id: uuid.UUID | None = None
    # WHO RULED ON THIS REQUEST, by name. Resolved from `manager_id` - which
    # `approve_leave_request`/`reject_leave_request` already stamp at decision
    # time - by `service._attach_employee_names`, so no column, no migration and
    # no second source of truth. None on a request nobody has decided yet, and on
    # the mutation responses, which don't run that batch lookup.
    manager_name: str | None = None
    manager_comment: str | None = None
    routed_project_id: uuid.UUID | None = None
    # WHO THE REQUEST WENT TO, by name - a SEPARATE FACT from `manager_name`:
    # the routed recipient and the person who ends up deciding may be different
    # people, and the card shows both.
    #
    # Answered by `service._attach_routed_to` for every pending, approved and
    # rejected request. A decided request reports the person its submission
    # notification actually reached, so a Head reassigned since cannot rewrite
    # who it was sent to; a pending one - and a decided one with no notification
    # on record - reports the routing chain itself, walked by the very same
    # `recipients.resolve_in_app_recipient` the notification walks.
    #
    # Populated by the DETAIL endpoint only; None on the list and the mutation
    # responses, and on the cancellation statuses, which show no actor row.
    routed_to_name: str | None = None
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
