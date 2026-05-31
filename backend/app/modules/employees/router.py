"""Employee endpoints (per openapi-v1.yaml).

  GET    /employees            list (RBAC-scoped) + search/filter/pagination
  POST   /employees            create (admin)
  GET    /employees/{id}       read (RBAC-scoped)
  PATCH  /employees/{id}       update (admin)
  DELETE /employees/{id}       deactivate / soft-delete (admin)
  GET    /employees/{id}/team  direct reports (admin / own manager)
"""
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.modules.employees import service
from app.modules.employees.models import EmployeeStatus
from app.modules.employees.schemas import (
    EmployeeCreate,
    EmployeeOut,
    EmployeePage,
    EmployeeUpdate,
)
from app.modules.users.models import User

router = APIRouter(prefix="/employees", tags=["employees"])


@router.get("", response_model=EmployeePage)
def list_employees(
    q: str | None = Query(default=None),
    status: EmployeeStatus | None = Query(default=None),
    department: str | None = Query(default=None),
    manager_id: uuid.UUID | None = Query(default=None),
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
    admin: User = Depends(require_role("admin")),
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
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> EmployeeOut:
    return EmployeeOut.model_validate(service.update_employee(db, admin, employee_id, body))


@router.delete("/{employee_id}", status_code=204)
def deactivate_employee(
    employee_id: uuid.UUID,
    admin: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
) -> Response:
    service.deactivate_employee(db, admin, employee_id)
    return Response(status_code=204)


@router.get("/{employee_id}/team", response_model=list[EmployeeOut])
def employee_team(
    employee_id: uuid.UUID,
    current: User = Depends(require_role("admin", "manager")),
    db: Session = Depends(get_db),
) -> list[EmployeeOut]:
    return [EmployeeOut.model_validate(e) for e in service.get_team(db, current, employee_id)]
