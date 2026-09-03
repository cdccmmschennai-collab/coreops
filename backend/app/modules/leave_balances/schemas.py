"""Leave balance pydantic schemas.

Every balance figure on the wire is a DERIVED month figure from
`leave_balances/ledger.py`, never a stored one. The month is carried explicitly
on each response so a client cannot mistake one month's balance for another's -
which is exactly the bug the attendance KPI had.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.shared.leave_units import validate_half_step

# DECIMAL(6,2) range on `employee_leave_adjustments.days`. Balances may be
# negative (loss-of-pay), e.g. -0.5 / -2, so the floor is deliberately negative
# and there is no non-negative validation anywhere in this module.
_LEAVE_MAX = 9999.99
_LEAVE_MIN = -9999.99
_REASON_MAX = 2000
_NOTE_MAX = 500

# `employee_leave_allocations.monthly_days` is NUMERIC(5,2) and CHECKed >= 0: an
# allocation is a grant, and a deduction is an adjustment. No upper policy limit
# is imposed here beyond the column's - 1, 2 and 3 are the values in use, but
# fractional and larger rates are valid and must not be hard-coded away.
_ALLOCATION_MAX = 999.99


def _assert_month_start(value: date) -> date:
    """A month key is always the first of its month.

    Mirrors the DB check constraints. Rejected rather than silently truncated:
    an API that quietly turns "effective from the 15th" into "effective from the
    1st" grants two weeks of leave nobody asked for.
    """
    if value.day != 1:
        raise ValueError("Must be the first day of a month, e.g. 2026-09-01.")
    return value


# ---------- reads -----------------------------------------------------------

class LeaveBalanceOut(BaseModel):
    """One employee's DERIVED balance for one month, with its working.

    Every term of `closing = carry_forward + allocation + adjustment - consumed`
    is reported, not just the total: the PM correcting a figure needs to see
    where it came from, and a card that shows only the total hides an accrual
    fault completely.
    """

    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    # The month this whole row describes. First of the month.
    month: date
    # The month's closing balance - the "Available Leave" figure.
    available_leave: float
    # The `Leave/month` in force for this month (0 when none is configured).
    monthly_allocation: float
    carry_forward: float
    adjustment: float
    consumed: float
    # False when the month precedes this employee's ledger. NOT the same as a
    # zero balance: there is no balance to state, and the UI shows "-".
    in_ledger: bool
    ledger_start_month: date | None = None
    last_updated: datetime | None = None


class LeaveBalancePage(BaseModel):
    items: list[LeaveBalanceOut]
    total: int
    limit: int
    offset: int
    # Echoed so a client can prove which month it is looking at.
    month: date


class MyLeaveBalanceOut(BaseModel):
    """The signed-in employee's own balance for one month (read-only)."""

    employee_id: uuid.UUID
    month: date
    available_leave: float
    monthly_allocation: float
    carry_forward: float
    adjustment: float
    consumed: float
    in_ledger: bool
    ledger_start_month: date | None = None
    last_updated: datetime | None = None


# ---------- PM correction ---------------------------------------------------

class LeaveBalanceUpdate(BaseModel):
    """The PM's manual correction, entered as the TARGET balance.

    Unchanged on the wire: the manager still types the number they want the
    employee to have, exactly as before. The service turns it into a signed
    adjustment (`target - the month's automatic balance`) so the correction sits
    beside the monthly allocation instead of destroying it.
    """

    available_leave: float = Field(ge=_LEAVE_MIN, le=_LEAVE_MAX)
    reason: str = Field(min_length=1, max_length=_REASON_MAX)
    # Which month the correction belongs to. Defaults to the current Chennai
    # business month, which is what the Leave Balance tab means by "now".
    month: date | None = None

    @field_validator("available_leave")
    @classmethod
    def _half_step(cls, value: float) -> float:
        """Leave is whole and half days only - 2.1 and 2.4 are not balances.

        Enforced HERE and not only by the dialog's `step="0.5"`, because the
        input attribute governs the arrows and nothing else: a typed value, a
        script, a replayed request or any other API client reaches this field
        directly, and a balance is exactly the kind of number that must not be
        quietly rounded on the way in.

        The bound is deliberately not applied to the negative floor - a
        loss-of-pay balance of -0.5 is as real as +0.5, and both are half steps.
        """
        return validate_half_step(value, "Available Leave")

    @field_validator("month")
    @classmethod
    def _month_start(cls, value: date | None) -> date | None:
        return None if value is None else _assert_month_start(value)


# ---------- PM allocation ---------------------------------------------------

class LeaveAllocationUpdate(BaseModel):
    """Set the employee's `Leave/month` from a given month onwards.

    Effective-dated on purpose: this writes a NEW row rather than editing the one
    in force, so raising somebody to 2 d/month in March leaves January and
    February on their old rate forever. Re-saving the SAME effective month
    updates that month's row - a correction to a decision, not a second competing
    decision.
    """

    monthly_days: float = Field(ge=0, le=_ALLOCATION_MAX)
    effective_from: date
    note: str | None = Field(default=None, max_length=_NOTE_MAX)

    @field_validator("monthly_days")
    @classmethod
    def _half_step(cls, value: float) -> float:
        """The accrual rate is in half days too.

        A rate of 1.75 d/month would mint balances that are not half steps
        however carefully every other write is validated - the accrual is added
        to the balance every month, so an invalid rate is an invalid balance
        forever. Validating the correction alone would leave that door open.
        """
        return validate_half_step(value, "Leave / month", minimum=0)

    @field_validator("effective_from")
    @classmethod
    def _month_start(cls, value: date) -> date:
        return _assert_month_start(value)


class LeaveAllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    effective_from: date
    monthly_days: float
    note: str | None = None
    created_by: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class LeaveAllocationPage(BaseModel):
    """Every rate this employee has ever been on, newest first."""

    items: list[LeaveAllocationOut]
    total: int


# ---------- history ---------------------------------------------------------

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
