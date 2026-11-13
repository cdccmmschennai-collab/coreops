"""Pydantic schemas for project deliverables."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.modules.project_deliverables import deadline
from app.modules.project_deliverables.models import DeliverableStatus

AssigneeRole = Literal["employee", "project_head"]


class DeliverableAssigneeOut(BaseModel):
    """One valid Assignee option: the project's Head or a project member."""

    employee_id: uuid.UUID
    name: str
    role: AssigneeRole


class DeliverableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str | None = None  # populated by service (global list only)
    project_code: str | None = None  # populated by service (global list only)
    name: str
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    owner_name: str | None = None   # populated by service
    # Assignee role, derived at read time (never stored): "project_head" when
    # the Assignee is the project's current Head, else "employee"; None = unassigned.
    owner_role: AssigneeRole | None = None
    status: DeliverableStatus
    completion_date: date | None = None
    created_at: datetime
    updated_at: datetime
    # Whether the CALLER may create/edit/delete deliverables on this row's
    # project (PM, or the project's assigned Head). Populated by the service;
    # the backend still enforces it on every write.
    can_manage: bool = False

    # Derived at read time from target_date + status + today (IST). Never stored
    # (ADR-003 Amendment 2) - see deadline.py for the ladder.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def days_remaining(self) -> int | None:
        return deadline.days_remaining(
            self.target_date, self.status, deadline.business_today()
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def deadline_state(self) -> deadline.DeadlineState:
        return deadline.deadline_state(
            self.target_date, self.status, deadline.business_today()
        )


class DeliverableCreate(BaseModel):
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    status: DeliverableStatus = DeliverableStatus.planned
    completion_date: date | None = None


class DeliverableUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = None
    planned_start_date: date | None = None
    target_date: date | None = None
    owner_employee_id: uuid.UUID | None = None
    status: DeliverableStatus | None = None
    completion_date: date | None = None
    # Mandatory when a tracked field (planned start date, due date, or a status
    # reversal from completed) changes; ignored otherwise.
    reason: str | None = Field(default=None, max_length=500)


class DeliverableChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deliverable_id: uuid.UUID
    field: str
    old_value: str | None = None
    new_value: str | None = None
    changed_by: uuid.UUID
    changed_by_name: str = ""   # populated by service join
    reason: str
    changed_at: datetime
