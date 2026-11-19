"""Rework Activity Approval - API schemas (Phase 3: review)."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReworkStatus = Literal["pending", "approved", "rejected", "cancelled"]


class ReworkRequestOut(BaseModel):
    id: uuid.UUID
    report_id: uuid.UUID | None
    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    project_id: uuid.UUID
    project_code: str | None
    project_name: str | None
    activity_id: uuid.UUID | None
    activity_name: str | None
    sub_activity_id: uuid.UUID
    sub_activity_name: str
    report_date: date
    day_part: str
    employee_remarks: str | None
    status: ReworkStatus
    cycle_no: int
    requested_at: datetime
    requested_by_name: str | None
    reviewer_name: str | None
    review_remarks: str | None
    decided_at: datetime | None
    # True when the CALLER may approve/reject this request right now.
    can_review: bool = False


class ReportActivityOut(BaseModel):
    """Another activity on the same daily report - context for the reviewer."""

    activity_name: str | None
    sub_activity_name: str | None
    project_code: str | None
    day_part: str | None
    description: str | None
    rework_approval_status: ReworkStatus | None


class ReworkRequestDetailOut(ReworkRequestOut):
    # Every cycle for this same report row, oldest first (includes this one).
    history: list[ReworkRequestOut]
    # The report's CURRENT status (draft while the employee is editing it).
    report_status: str | None
    report_activities: list[ReportActivityOut]


class ReworkCounts(BaseModel):
    pending: int
    approved: int
    rejected: int


class ReworkRequestPage(BaseModel):
    items: list[ReworkRequestOut]
    total: int
    limit: int
    offset: int
    counts: ReworkCounts


class FilterOption(BaseModel):
    value: uuid.UUID
    label: str


class ReworkFilterOptions(BaseModel):
    projects: list[FilterOption]
    employees: list[FilterOption]
    activities: list[FilterOption]


class ReworkDecisionIn(BaseModel):
    remarks: str | None = Field(default=None, max_length=2000)

    @field_validator("remarks")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = (v or "").strip()
        return v or None
