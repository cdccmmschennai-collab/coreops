"""Plant master data pydantic schemas."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PlanningPlantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str
    is_active: bool
    created_at: datetime


class MaintenancePlantOut(BaseModel):
    """Flattened with the parent Planning Plant's code/description — the
    shape both the Project form and the Work Report row need (pick the
    Maintenance Plant, auto-show the Planning Plant info)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    description: str | None
    planning_plant_id: uuid.UUID
    planning_plant_code: str
    planning_plant_description: str
    is_active: bool
