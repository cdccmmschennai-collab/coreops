"""Plant master data endpoints (read-only).

  GET /plants/planning-plants     list Planning Plants
  GET /plants/maintenance-plants  list Maintenance Plants, flattened with
                                   their parent Planning Plant's code/description
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.plants import service
from app.modules.plants.schemas import MaintenancePlantOut, PlanningPlantOut
from app.modules.users.models import User

router = APIRouter(prefix="/plants", tags=["plants"])


@router.get("/planning-plants", response_model=list[PlanningPlantOut])
def list_planning_plants(
    active_only: bool = Query(default=True),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PlanningPlantOut]:
    rows = service.list_planning_plants(db, active_only=active_only)
    return [PlanningPlantOut.model_validate(r) for r in rows]


@router.get("/maintenance-plants", response_model=list[MaintenancePlantOut])
def list_maintenance_plants(
    active_only: bool = Query(default=True),
    planning_plant_code: str | None = Query(
        default=None,
        description="Return only Maintenance Plants belonging to this Planning Plant code "
        "(e.g. '2400'). Used by the project-scoped dropdown on the work-report form.",
    ),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MaintenancePlantOut]:
    rows = service.list_maintenance_plants(
        db, active_only=active_only, planning_plant_code=planning_plant_code
    )
    return [MaintenancePlantOut.model_validate(r) for r in rows]
