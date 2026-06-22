"""Plant master data service — read-only lookups.

No write endpoints yet (static SAP reference data, seeded via
scripts/seed_plants.py). RBAC: any authenticated user can read — these are
just dropdown options for the Project and Work Report forms, same as
job_codes/activity_master.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, aliased

from app.modules.plants.models import MaintenancePlant, PlanningPlant
from app.shared.errors import AppError


def list_planning_plants(db: Session, *, active_only: bool = True) -> list[PlanningPlant]:
    stmt = select(PlanningPlant)
    if active_only:
        stmt = stmt.where(PlanningPlant.is_active.is_(True))
    stmt = stmt.order_by(PlanningPlant.code)
    return list(db.execute(stmt).scalars().all())


def list_maintenance_plants(
    db: Session,
    *,
    active_only: bool = True,
    planning_plant_code: str | None = None,
) -> list[dict]:
    """List Maintenance Plants, flattened with their parent Planning Plant.

    When `planning_plant_code` is given, only the Maintenance Plants belonging
    to that Planning Plant are returned — the project-scoped dropdown for the
    work-report form (a user must never see plants from other Planning Plants).
    """
    Parent = aliased(PlanningPlant)
    stmt = select(MaintenancePlant, Parent.code, Parent.description).join(
        Parent, MaintenancePlant.planning_plant_id == Parent.id
    )
    if active_only:
        stmt = stmt.where(MaintenancePlant.is_active.is_(True), Parent.is_active.is_(True))
    if planning_plant_code is not None:
        stmt = stmt.where(Parent.code == planning_plant_code.strip())
    stmt = stmt.order_by(Parent.code, MaintenancePlant.code)
    rows = db.execute(stmt).all()
    return [
        {
            "id": mp.id,
            "code": mp.code,
            "description": mp.description,
            "planning_plant_id": mp.planning_plant_id,
            "planning_plant_code": pp_code,
            "planning_plant_description": pp_description,
            "is_active": mp.is_active,
        }
        for mp, pp_code, pp_description in rows
    ]


def get_maintenance_plant(db: Session, maintenance_plant_id: uuid.UUID) -> MaintenancePlant:
    row = db.get(MaintenancePlant, maintenance_plant_id)
    if row is None or not row.is_active:
        raise AppError("validation_error", "Selected maintenance plant is invalid or inactive.", 422)
    return row
