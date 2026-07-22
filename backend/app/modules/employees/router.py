"""Employee endpoints (per openapi-v1.yaml).

  GET    /employees                        list (RBAC-scoped) + search/filter/pagination
  POST   /employees                        create (admin)
  GET    /employees/{id}                   read (RBAC-scoped)
  PATCH  /employees/{id}                   update (admin)
  DELETE /employees/{id}                   deactivate / soft-delete (admin)
  GET    /employees/{id}/team              direct reports (admin)
  POST   /employees/{id}/account           create + link login account (admin)
  PATCH  /employees/{id}/account/password  reset linked account password (admin)
  PATCH  /employees/{id}/account/status    enable / disable linked account (admin)
  PATCH  /employees/{id}/account/role      change linked account role (admin)
  PATCH  /employees/{id}/account/link      relink to a different user (admin)
  DELETE /employees/{id}/account/link      unlink the account (admin)
"""
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.employees import service
from app.modules.employees.models import EmployeeStatus
from app.modules.employees.schemas import (
    AccountCreate,
    AccountLink,
    AccountPasswordReset,
    AccountRoleUpdate,
    AccountStatusUpdate,
    EmployeeCreate,
    EmployeeOut,
    EmployeePage,
    EmployeeUpdate,
)
from app.modules.users.models import User
from app.modules.users.schemas import UserOut

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeePage)
def list_employees(
    q: str | None = Query(default=None),
    status: EmployeeStatus | None = Query(default=None),
    department: str | None = Query(default=None),
    manager_id: uuid.UUID | None = Query(default=None),
    exclude_activity_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeePage:
    rows, total = service.list_employees(
        db,
        current,
        q=q,
        status=status,
        department=department,
        manager_id=manager_id,
        limit=limit,
        offset=offset,
        exclude_activity_id=exclude_activity_id,
    )
    return EmployeePage(
        items=[EmployeeOut.model_validate(e) for e in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=EmployeeOut, status_code=201)
def create_employee(
    body: EmployeeCreate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return EmployeeOut.model_validate(service.create_employee(db, admin, body))


@router.get("/{employee_id}", response_model=EmployeeOut)
def get_employee(
    employee_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return EmployeeOut.model_validate(service.get_employee(db, current, employee_id))


@router.patch("/{employee_id}", response_model=EmployeeOut)
def update_employee(
    employee_id: uuid.UUID,
    body: EmployeeUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return EmployeeOut.model_validate(service.update_employee(db, admin, employee_id, body))


@router.delete("/{employee_id}", status_code=204)
def deactivate_employee(
    employee_id: uuid.UUID,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.deactivate_employee(db, admin, employee_id)
    return Response(status_code=204)


@router.get("/{employee_id}/team", response_model=list[EmployeeOut])
def employee_team(
    employee_id: uuid.UUID,
    current: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> list[EmployeeOut]:
    return [EmployeeOut.model_validate(e) for e in service.get_team(db, current, employee_id)]


# ---------- account management (project_manager only) ----------

@router.post("/{employee_id}/account", response_model=UserOut, status_code=201)
def create_employee_account(
    employee_id: uuid.UUID,
    body: AccountCreate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.create_and_link_account(db, admin, employee_id, body))


@router.patch("/{employee_id}/account/password", status_code=204)
def reset_employee_account_password(
    employee_id: uuid.UUID,
    body: AccountPasswordReset,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.reset_account_password(db, admin, employee_id, body)
    return Response(status_code=204)


@router.patch("/{employee_id}/account/status", response_model=UserOut)
def update_employee_account_status(
    employee_id: uuid.UUID,
    body: AccountStatusUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.update_account_status(db, admin, employee_id, body))


@router.patch("/{employee_id}/account/role", response_model=UserOut)
def change_employee_account_role(
    employee_id: uuid.UUID,
    body: AccountRoleUpdate,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.change_account_role(db, admin, employee_id, body))


@router.patch("/{employee_id}/account/link", response_model=UserOut)
def relink_employee_account(
    employee_id: uuid.UUID,
    body: AccountLink,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.relink_account(db, admin, employee_id, body))


@router.delete("/{employee_id}/account/link", status_code=204)
def unlink_employee_account(
    employee_id: uuid.UUID,
    admin: User = Depends(require_role("project_manager")),
    db: Session = Depends(get_db),
) -> Response:
    service.unlink_account(db, admin, employee_id)
    return Response(status_code=204)
