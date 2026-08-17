"""Permission Request pydantic schemas."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.modules.permissions.models import PermissionStatus

_REASON_MAX = 2000
_COMMENT_MAX = 1000


class PermissionRequestCreate(BaseModel):
    permission_date: date
    # `Literal[1, 2]` rather than a bounded int: it rejects 0, 3 and any decimal
    # at the edge of the API and puts the two legal values in the OpenAPI schema,
    # so the "no 30-minute permission" rule is documented, not just enforced.
    duration_hours: Literal[1, 2]
    reason: str | None = Field(default=None, max_length=_REASON_MAX)


class PermissionReviewBody(BaseModel):
    comment: str | None = Field(default=None, max_length=_COMMENT_MAX)


class PermissionRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    permission_date: date
    duration_hours: int
    reason: str | None = None
    status: PermissionStatus
    manager_id: uuid.UUID | None = None
    manager_comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PermissionRequestPage(BaseModel):
    items: list[PermissionRequestOut]
    total: int
    limit: int
    offset: int


class PermissionBalanceOut(BaseModel):
    """One employee's permission standing for one calendar month.

    `remaining_hours` is derived server-side and is the only figure any decision
    is made against - the frontend's preview is a convenience, never an input.
    """

    employee_id: uuid.UUID
    month: date  # first day of the month
    allowance_hours: int
    approved_hours: int
    remaining_hours: int


class PermissionRequestBalanceOut(BaseModel):
    """The month's standing AND this request's place in it, for the detail page.

    Every figure is computed server-side from the same derivation as everything
    else, so the detail page does no arithmetic of its own. The point of the
    request-specific fields is to be able to state what a request actually cost
    WITHOUT pretending: only an approved request has consumed anything, so
    `consumed_by_request` is 0 for pending, rejected and cancelled alike.

    `remaining_before_request` is "what this month would have if this request did
    not exist" - not a replay of the historical figure at the instant of
    approval, which later approvals would have moved and which only the audit log
    can answer. For an approved request the two coincide whenever it was the last
    one decided, and the derived form is stable rather than guessed.
    """

    month: date
    allowance_hours: int
    # The month's totals, across every request in it.
    approved_hours: int
    remaining_hours: int
    # This request's own contribution.
    consumed_by_request: int
    remaining_before_request: int
    # Pending only: what approving it would leave. None for a settled request,
    # so the UI cannot present a decided request as if it were still a forecast.
    remaining_if_approved: int | None = None


class PermissionRequestDetailOut(PermissionRequestOut):
    """One request with everything the detail page shows, resolved server-side.

    The names are here rather than looked up in the browser because the employee
    list endpoint is manager-scoped: an employee opening their OWN request has no
    way to resolve a name through it. Sending them with the request also means the
    page needs exactly one call.
    """

    employee_name: str | None = None
    employee_code: str | None = None
    reviewer_name: str | None = None
    balance: PermissionRequestBalanceOut


class PermissionHistoryOut(BaseModel):
    """One month of an employee's permission history, with that month's balance.

    Returned together on purpose: the history table and the "2h / 4h" figure above
    it describe the same month, and computing the month's bounds in one place -
    here, from `balance.month_bounds` - is what keeps the client from deriving a
    second answer.
    """

    employee_id: uuid.UUID
    month: date  # first day of the month
    balance: PermissionBalanceOut
    items: list[PermissionRequestOut]
    total: int
