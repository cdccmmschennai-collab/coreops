"""Comp Off Request pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.comp_off.models import CompOffStatus

_REASON_MAX = 2000
_COMMENT_MAX = 1000


class CompOffRequestCreate(BaseModel):
    # No employee id: the requester is always the authenticated caller.
    worked_date: date
    off_date: date
    reason: str | None = Field(default=None, max_length=_REASON_MAX)

    @model_validator(mode="after")
    def _dates_differ(self) -> "CompOffRequestCreate":
        if self.worked_date == self.off_date:
            raise ValueError("The day you worked and the day off must be different dates.")
        return self


class CompOffApproveBody(BaseModel):
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX)


class CompOffRejectBody(BaseModel):
    # Required, and required to say something: a rejection with no reason gives
    # the employee nothing to act on.
    reason: str = Field(max_length=_COMMENT_MAX)

    @field_validator("reason")
    @classmethod
    def _reason_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("A reason is required to reject a comp off request.")
        return value


class CompOffRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    # Resolved server-side by `service._attach_names`; None on mutation responses.
    employee_name: str | None = None
    worked_date: date
    off_date: date
    reason: str | None = None
    status: CompOffStatus
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    manager_comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CompOffRequestPage(BaseModel):
    items: list[CompOffRequestOut]
    total: int
    limit: int
    offset: int
