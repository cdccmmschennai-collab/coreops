"""Leave balance pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# DECIMAL(5,2) range. Balances may be negative (loss-of-pay), e.g. -0.5 / -2.
_LEAVE_MAX = 999.99
_LEAVE_MIN = -999.99
_REASON_MAX = 2000


class LeaveBalanceOut(BaseModel):
    """One employee's balance row for the manager list."""
    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    available_leave: float
    last_updated: datetime | None = None


class LeaveBalancePage(BaseModel):
    items: list[LeaveBalanceOut]
    total: int
    limit: int
    offset: int


class LeaveBalanceUpdate(BaseModel):
    available_leave: float = Field(ge=_LEAVE_MIN, le=_LEAVE_MAX)
    reason: str = Field(min_length=1, max_length=_REASON_MAX)


class MyLeaveBalanceOut(BaseModel):
    """The signed-in employee's own available leave (read-only)."""
    employee_id: uuid.UUID
    available_leave: float
    last_updated: datetime | None = None


class LeaveBalanceHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    old_balance: float | None = None
    new_balance: float
    reason: str
    updated_by: uuid.UUID | None = None
    updated_by_name: str | None = None
    created_at: datetime


class LeaveBalanceHistoryPage(BaseModel):
    items: list[LeaveBalanceHistoryOut]
    total: int
    limit: int
    offset: int
