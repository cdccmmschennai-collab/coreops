"""Project pydantic schemas."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.models import (
    ActivityMemberRole,
    ProjectMemberRole,
    ProjectStatus,
)


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


class ActivityMemberOut(BaseModel):
    """One person's staffing on one project activity."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    activity_id: uuid.UUID
    employee_id: uuid.UUID
    employee_name: str = ""   # populated by service join
    role: ActivityMemberRole
    is_qc: bool
    created_at: datetime


class ActivityMemberCreate(BaseModel):
    employee_id: uuid.UUID
    role: ActivityMemberRole
    is_qc: bool = False


class ActivityMemberUpdate(BaseModel):
    # Both optional: change the base role and/or toggle QC. Omitted fields are
    # left unchanged (promotion to lead is Head-only, enforced in the service).
    role: ActivityMemberRole | None = None
    is_qc: bool | None = None


class ActivityStaffingOut(BaseModel):
    """One project activity with its resolved staffing (Lead, the Contributor
    list, and which members hold QC). Named distinctly from the unrelated
    project_activities.ProjectActivityOut (the planning work-item feature)."""
    activity_id: uuid.UUID
    activity_code: str | None = None   # populated by service join (activity_master.code)
    activity_name: str = ""   # populated by service join (activity_master.name)
    lead: ActivityMemberOut | None = None
    contributors: list[ActivityMemberOut] = Field(default_factory=list)
    qc: list[ActivityMemberOut] = Field(default_factory=list)
    member_count: int = 0


class ProjectHeadUpdate(BaseModel):
    # null clears the Head; otherwise the employee assigned as project Head.
    head_employee_id: uuid.UUID | None = None


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
