"""Auth endpoints: login, logout, current user (per openapi-v1.yaml)."""
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_claims, get_current_user
from app.core.security import revoke_token
from app.modules.auth import service
from app.modules.users.models import User
from app.modules.users.schemas import LoginRequest, Me, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    ip = request.client.host if request.client else "unknown"
    token, expires_in = service.authenticate(db, body.email, body.password, ip)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/logout", status_code=204)
def logout(claims: dict = Depends(get_current_claims)) -> Response:
    revoke_token(claims["jti"], claims["exp"])
    return Response(status_code=204)


@router.get("/me", response_model=Me)
def me(current: User = Depends(get_current_user)) -> Me:
    return Me(user=UserOut.model_validate(current))
