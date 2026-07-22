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
from app.modules.activity_master import access_service, service
from app.modules.activity_master.access_schemas import (
    ActivityAccessConfigOut,
    ChangeAccessTypeIn,
    GrantAccessIn,
    GrantResultOut,
)
from app.modules.activity_master.schemas import (
    ActivityCreate,
    ActivityMasterOut,
    ActivityMasterUpdate,
    SubActivityCreate,
    SubActivityFlatOut,
)
from app.modules.employees.service import _current_employee
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
    user: User = AuthUser,
    db: Session = Depends(get_db),
) -> list[SubActivityFlatOut]:
    # Restricted-activity filtering: an employee (including a PM filing their own
    # report) only sees COMMON sub-activities plus RESTRICTED ones they've been
    # granted. The employee is derived from the authenticated identity — never
    # client-supplied. A user with no employee profile sees only COMMON.
    employee = _current_employee(db, user)
    rows = service.list_all_sub_activities_flat(
        db, active_only=active_only, employee_id=employee.id if employee else None
    )
    return [SubActivityFlatOut.model_validate(r) for r in rows]


# ── activity access control (PM-only, migration 0061) ────────────────────────

@router.get("/activities/{activity_id}/access", response_model=ActivityAccessConfigOut)
def get_activity_access(
    activity_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> ActivityAccessConfigOut:
    return ActivityAccessConfigOut.model_validate(
        access_service.list_activity_access(
            db, activity_id=activity_id, limit=limit, offset=offset
        )
    )


@router.patch("/activities/{activity_id}/access-type", response_model=GrantResultOut)
def change_activity_access_type(
    activity_id: uuid.UUID,
    body: ChangeAccessTypeIn,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> GrantResultOut:
    return GrantResultOut.model_validate(
        access_service.change_activity_access_type(
            db,
            actor=admin,
            activity_id=activity_id,
            new_type=body.access_type,
            employee_ids=body.employee_ids,
        )
    )


@router.post("/activities/{activity_id}/access", response_model=GrantResultOut)
def grant_activity_access(
    activity_id: uuid.UUID,
    body: GrantAccessIn,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> GrantResultOut:
    return GrantResultOut.model_validate(
        access_service.grant_activity_access(
            db, actor=admin, activity_id=activity_id, employee_ids=body.employee_ids
        )
    )


@router.delete("/activities/{activity_id}/access/{employee_id}")
def revoke_activity_access(
    activity_id: uuid.UUID,
    employee_id: uuid.UUID,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> dict:
    return access_service.revoke_activity_access(
        db, actor=admin, activity_id=activity_id, employee_id=employee_id
    )


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
