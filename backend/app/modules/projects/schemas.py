"""Project pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.models import ProjectMemberRole, ProjectStatus


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    job_code_id: uuid.UUID | None = None
    job_code_code: str | None = None   # populated by service join
    job_code_name: str | None = None   # populated by service join
    planning_plant_id: uuid.UUID | None = None
    maintenance_plant_id: uuid.UUID | None = None
    maintenance_plant_code: str | None = None          # populated by service join
    maintenance_plant_description: str | None = None   # populated by service join
    planning_plant_code: str | None = None              # populated by service join
    planning_plant_description: str | None = None       # populated by service join
    head_employee_id: uuid.UUID | None = None
    head_employee_name: str | None = None               # populated by service join
    client: str | None = None
    description: str | None = None
    status: ProjectStatus
    start_date: date | None = None
    planned_completion_date: date | None = None
    actual_completion_date: date | None = None
    days_running: int | None = None   # populated by service (today - start_date)
    member_count: int = 0
    created_at: datetime


class ProjectCreate(BaseModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    job_code: str | None = None   # free text; resolved to a JobCode by the service
    planning_plant_id: uuid.UUID | None = None   # project master link to a Planning Plant
    maintenance_plant_id: uuid.UUID | None = None
    client: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.planning
    start_date: date | None = None
    planned_completion_date: date | None = None
    actual_completion_date: date | None = None


class ProjectUpdate(BaseModel):
    code: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    job_code: str | None = None   # free text; resolved to a JobCode by the service
    planning_plant_id: uuid.UUID | None = None   # project master link to a Planning Plant
    maintenance_plant_id: uuid.UUID | None = None
    client: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None
    start_date: date | None = None
    actual_completion_date: date | None = None
    # Allowed only for initial set (when the project has no planned date yet).
    # Use PATCH /projects/{id}/planned-completion-date (with reason) for subsequent changes.
    planned_completion_date: date | None = None


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    total: int
    limit: int
    offset: int


class ProjectMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str
    role: ProjectMemberRole
    created_at: datetime


class ProjectMemberCreate(BaseModel):
    employee_id: uuid.UUID
    role: ProjectMemberRole = ProjectMemberRole.contributor


class ProjectMemberRoleUpdate(BaseModel):
    role: ProjectMemberRole


class LedProjectMember(BaseModel):
    employee_id: uuid.UUID
    name: str


class LedProject(BaseModel):
    project_id: uuid.UUID
    name: str
    code: str
    members: list[LedProjectMember]


class TimelineEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    event_type: str
    actor_id: uuid.UUID | None
    actor_name: str | None
    details: dict
    created_at: datetime


class PlannedDateUpdate(BaseModel):
    new_date: date | None = None
    reason: str = Field(min_length=1, max_length=500)


class PlannedDateChangeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    old_date: date | None
    new_date: date | None
    changed_by: uuid.UUID
    changed_by_name: str = ""   # populated by service join
    reason: str
    changed_at: datetime
