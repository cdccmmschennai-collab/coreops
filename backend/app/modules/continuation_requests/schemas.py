"""ContinuationRequest pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.modules.continuation_requests.models import ContinuationRequestStatus


class ContinuationRequestCreate(BaseModel):
    """Body sent when an employee clicks 'Request Continuation Approval'."""
    work_item_id: uuid.UUID
    continuation_date: date


class ContinuationReviewBody(BaseModel):
    comment: str | None = None


class ContinuationRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    work_item_id: uuid.UUID
    project_id: uuid.UUID
    sub_activity_id: uuid.UUID
    original_report_date: date
    allowed_duration_days: int
    due_date: date
    continuation_date: date
    status: ContinuationRequestStatus
    requested_at: datetime
    reviewer_id: uuid.UUID | None = None
    decision_comment: str | None = None
    decided_at: datetime | None = None

    # Display-only, resolved by the service (never persisted).
    employee_name: str = ""
    project_name: str = ""
    project_code: str = ""
    activity_name: str | None = None
    sub_activity_name: str = ""
    reviewer_name: str | None = None
    # Who this request is CURRENTLY routed to - resolved fresh at read time,
    # never frozen (matches leave's routing model, spec section 14).
    routed_to_name: str | None = None
    routed_to_role: str | None = None  # "head" | "manager" | None


class ContinuationRequestPage(BaseModel):
    items: list[ContinuationRequestOut] = []
    total: int
    limit: int
    offset: int
