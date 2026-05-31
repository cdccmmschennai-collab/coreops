"""User administration endpoints (admin-only) — per openapi-v1.yaml."""
import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.users import service
from app.modules.users.models import User
from app.modules.users.schemas import (
    PasswordUpdate,
    RoleUpdate,
    UserCreate,
    UserOut,
    UserPage,
    UserUpdate,
)

router = APIRouter(prefix="/users", tags=["users"])

# Every endpoint here requires the admin role.
AdminUser = Depends(require_role("admin"))


@router.get("", response_model=UserPage)
def list_users(
    q: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> UserPage:
    rows, total = service.list_users(db, q, limit, offset)
    return UserPage(
        items=[UserOut.model_validate(u) for u in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    body: UserCreate, _admin: User = AdminUser, db: Session = Depends(get_db)
) -> UserOut:
    return UserOut.model_validate(service.create_user(db, body))


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
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> Response:
    service.set_password(db, user_id, body.new_password)
    return Response(status_code=204)
