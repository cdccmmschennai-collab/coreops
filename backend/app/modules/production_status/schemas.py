"""Production Status pydantic schemas.

The read schema is deliberately flat and fully resolved: project/plant labels,
the activity name and the author's full name are all included, so a client
never has to turn a user id into a person or a project id into a plant.
"""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# Mirrors VALID_PRODUCTION_STATUSES in models.py; kept as a Literal so an
# unknown status is rejected as a 422 by FastAPI before it reaches the service.
ProductionStatusValue = Literal["in_progress", "closed"]


class ProductionStatusCreate(BaseModel):
    # Project is NEVER supplied in the body - it comes from the path, which is
    # what the caller is authorized against. Plant information is derived from
    # the project, so it is not accepted here either.
    revision: str = Field(min_length=1, max_length=50)
    activity_id: uuid.UUID
    status: ProductionStatusValue
    # Four independent units; same `default=0, ge=0` convention the work report
    # task schema uses for its counts.
    tag_count: int = Field(default=0, ge=0)
    doc_count: int = Field(default=0, ge=0)
    spares_count: int = Field(default=0, ge=0)
    crs_count: int = Field(default=0, ge=0)
    completed_on: date | None = None
    remarks: str | None = None


class ProductionStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID

    # --- project / plant (derived from the project, never entered) ---------
    project_id: uuid.UUID
    project_code: str
    project_name: str
    planning_plant_code: str | None = None
    planning_plant_description: str | None = None
    maintenance_plant_code: str | None = None
    maintenance_plant_description: str | None = None

    revision: str

    # --- activity (activity_master) ---------------------------------------
    activity_id: uuid.UUID
    activity_name: str | None = None
    activity_code: str | None = None

    status: str
    tag_count: int
    doc_count: int
    spares_count: int
    crs_count: int
    completed_on: date | None = None
    remarks: str | None = None

    # --- author: the real person, resolved server-side --------------------
    created_by: uuid.UUID
    created_by_name: str = ""
    created_at: datetime
