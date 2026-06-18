"""User administration endpoints (admin-only) — per openapi-v1.yaml."""
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.users import service
from app.modules.users.models import User
from app.modules.users.schemas import (
    LinkedEmployee,
    PasswordUpdate,
    RoleUpdate,
    UserCreate,
    UserListItem,
    UserOut,
    UserPage,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

AdminUser = Depends(require_role("project_manager"))


@router.get("", response_model=UserPage)
def list_users(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> UserPage:
    rows, total, emp_map = service.list_users(db, q, limit, offset)
    items: list[UserListItem] = []
    for u in rows:
        emp = emp_map.get(u.id)
        items.append(
            UserListItem(
                **UserOut.model_validate(u).model_dump(),
                linked_employee=(
                    LinkedEmployee.model_validate(emp) if emp is not None else None
                ),
            )
        )
    return UserPage(items=items, total=total, limit=limit, offset=offset)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, admin: User = AdminUser, db: Session = Depends(get_db)
) -> UserOut:
    return UserOut.model_validate(service.create_user(db, body, admin))


@router.get("/{user_id}", response_model=UserOut)
def get_user(
    user_id: uuid.UUID, _admin: User = AdminUser, db: Session = Depends(get_db)
) -> UserOut:
    return UserOut.model_validate(service.get_user(db, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.update_user(db, user_id, body, admin))


@router.patch("/{user_id}/role", response_model=UserOut)
def set_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> UserOut:
    return UserOut.model_validate(service.set_role(db, user_id, body.role, admin))


@router.patch("/{user_id}/password", status_code=204)
def set_password(
    user_id: uuid.UUID,
    body: PasswordUpdate,
    admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> Response:
    service.set_password(db, user_id, body.new_password, admin)
    return Response(status_code=204)
