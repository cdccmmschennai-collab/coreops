"""Auth endpoints: login, logout, current user (per openapi-v1.yaml)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_claims, get_current_user
from app.core.security import revoke_token
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType
from app.modules.auth import service
from app.modules.employees.service import _current_employee, build_profile
from app.modules.users.models import User
from app.modules.users.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    Me,
    TokenResponse,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    token, expires_in = service.authenticate(db, body.email, body.password, ip)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", status_code=204)
def logout(
    claims: dict = Depends(get_current_claims),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    revoke_token(claims["jti"], claims["exp"])
    audit.record_audit(
        db,
        action=AuditAction.LOGOUT,
        actor=current,
        entity_type=EntityType.USER,
        entity_id=current.id,
        commit=True,
    )
    return Response(status_code=204)


@router.post("/change-password", status_code=204)
def change_password(
    body: ChangePasswordRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    service.change_password(db, current, body.current_password, body.new_password)
    return Response(status_code=204)


@router.get("/me", response_model=Me)
def me(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Me:
    employee = _current_employee(db, current)
    return Me(
        user=UserOut.model_validate(current),
        employee=build_profile(db, employee) if employee else None,
        employee_id=employee.id if employee else None,
    )
