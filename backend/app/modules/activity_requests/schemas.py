"""ActivityRequest pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.activity_requests.models import ActivityRequestStatus


class ActivityRequestCreate(BaseModel):
    """Body sent when an employee clicks 'Request PM to Add Another Activity'.

    Carries the currently-selected activity row's details verbatim. No approval
    fields, no reason/remarks.
    """
    report_id: uuid.UUID
    project_id: uuid.UUID
    activity_id: uuid.UUID | None = None
    sub_activity_id: uuid.UUID
    # Requested workload hints only — six units, same shape/validation as the
    # work-report row they become on approval. These never create benchmark
    # performance, complete a task, or affect pending calculations.
    tags_count: int = Field(default=0, ge=0)
    docs_count: int = Field(default=0, ge=0)
    bom_count: int = Field(default=0, ge=0)
    spares_count: int = Field(default=0, ge=0)
    pages_count: int = Field(default=0, ge=0)
    records_count: int = Field(default=0, ge=0)


class ActivityRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    employee_id: uuid.UUID
    report_id: uuid.UUID | None
    project_id: uuid.UUID
    activity_id: uuid.UUID | None
    sub_activity_id: uuid.UUID
    tags_count: int
    docs_count: int
    bom_count: int
    spares_count: int
    pages_count: int
    records_count: int
    status: ActivityRequestStatus
    requested_at: datetime
    approved_by: uuid.UUID | None
    approved_at: datetime | None

    # Display-only names resolved by the service (never persisted).
    employee_name: str = ""
    project_name: str = ""
    project_code: str = ""
    activity_name: str | None = None
    sub_activity_name: str = ""
    task_title: str | None = None

    # The employee's currently-logged (first) activity in the report — shown to
    # the PM alongside the requested activity so they can compare. Resolved by
    # the service; None when the report has no activity row yet.
    current_project_name: str | None = None
    current_project_code: str | None = None
    current_activity_name: str | None = None
    current_sub_activity_name: str | None = None
