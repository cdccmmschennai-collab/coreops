"""ActivityMaster endpoints.

  GET    /activity-master/activities                         list Activities (auth)
  POST   /activity-master/activities                         create Activity (PM)
  PATCH  /activity-master/activities/{id}                    update (PM)
  DELETE /activity-master/activities/{id}                    soft-deactivate (PM)

  GET    /activity-master/activities/{id}/sub-activities      list children (auth)
  POST   /activity-master/activities/{id}/sub-activities      create under parent (PM)

  PATCH  /activity-master/sub-activities/{id}                 update (PM)
  DELETE /activity-master/sub-activities/{id}                 soft-deactivate (PM)
  GET    /activity-master/sub-activities                      flat list-all, for dropdowns (auth)
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.activity_master import service
from app.modules.activity_master.schemas import (
    ActivityCreate,
    ActivityMasterOut,
    ActivityMasterUpdate,
    SubActivityCreate,
    SubActivityFlatOut,
)
from app.modules.users.models import User

router = APIRouter(prefix="/activity-master", tags=["activity-master"])

AdminUser = Depends(require_role("project_manager"))
AuthUser = Depends(get_current_user)


@router.get("/activities", response_model=list[ActivityMasterOut])
def list_activities(
    active_only: bool = Query(default=True),
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> list[ActivityMasterOut]:
    rows = service.list_activities(db, active_only=active_only)
    return [ActivityMasterOut.model_validate(r) for r in rows]


@router.post("/activities", response_model=ActivityMasterOut, status_code=201)
def create_activity(
    body: ActivityCreate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.create_activity(db, body, created_by=admin.id)
    )


@router.get("/activities/{activity_id}/sub-activities", response_model=list[ActivityMasterOut])
def list_sub_activities(
    activity_id: uuid.UUID,
    active_only: bool = Query(default=True),
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> list[ActivityMasterOut]:
    rows = service.list_sub_activities(db, activity_id, active_only=active_only)
    return [ActivityMasterOut.model_validate(r) for r in rows]


@router.post(
    "/activities/{activity_id}/sub-activities",
    response_model=ActivityMasterOut,
    status_code=201,
)
def create_sub_activity(
    activity_id: uuid.UUID,
    body: SubActivityCreate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.create_sub_activity(db, activity_id, body, created_by=admin.id)
    )


@router.get("/sub-activities", response_model=list[SubActivityFlatOut])
def list_all_sub_activities_flat(
    active_only: bool = Query(default=True),
    _user: User = AuthUser,
    db: Session = Depends(get_db),
) -> list[SubActivityFlatOut]:
    rows = service.list_all_sub_activities_flat(db, active_only=active_only)
    return [SubActivityFlatOut.model_validate(r) for r in rows]


@router.patch("/activities/{activity_master_id}", response_model=ActivityMasterOut)
def update_activity(
    activity_master_id: uuid.UUID,
    body: ActivityMasterUpdate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.update_activity_master(db, activity_master_id, body)
    )


@router.delete("/activities/{activity_master_id}", response_model=ActivityMasterOut)
def deactivate_activity(
    activity_master_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.deactivate_activity_master(db, activity_master_id)
    )


@router.patch("/sub-activities/{activity_master_id}", response_model=ActivityMasterOut)
def update_sub_activity(
    activity_master_id: uuid.UUID,
    body: ActivityMasterUpdate,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.update_activity_master(db, activity_master_id, body)
    )


@router.delete("/sub-activities/{activity_master_id}", response_model=ActivityMasterOut)
def deactivate_sub_activity(
    activity_master_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityMasterOut:
    return ActivityMasterOut.model_validate(
        service.deactivate_activity_master(db, activity_master_id)
    )
