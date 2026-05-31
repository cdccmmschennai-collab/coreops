"""Shared FastAPI dependencies: DB session + authentication/authorization.

  get_current_claims  -> decoded, non-revoked JWT claims
  get_current_user    -> the active User for those claims
  require_role(*roles)-> dependency factory enforcing a coarse role gate
"""
import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import TokenError, decode_token, is_revoked
from app.modules.users.models import User, UserRole
from app.shared.errors import AppError

__all__ = ["get_db", "get_current_claims", "get_current_user", "require_role"]

_bearer = HTTPBearer(auto_error=False)


def get_current_claims(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    if creds is None or not creds.credentials:
        raise AppError("unauthorized", "Not authenticated.", 401)
    try:
        claims = decode_token(creds.credentials)
    except TokenError:
        raise AppError("unauthorized", "Invalid or expired token.", 401)
    if is_revoked(claims.get("jti", "")):
        raise AppError("unauthorized", "Token has been revoked.", 401)
    return claims


def get_current_user(
    claims: dict = Depends(get_current_claims),
    db: Session = Depends(get_db),
) -> User:
    try:
        user_id = uuid.UUID(str(claims.get("sub")))
    except (ValueError, TypeError):
        raise AppError("unauthorized", "Malformed token subject.", 401)
    user = db.get(User, user_id)
    if user is None or user.deleted_at is not None or not user.is_active:
        raise AppError("unauthorized", "User is inactive or not found.", 401)
    return user


def require_role(*roles: UserRole | str):
    allowed = {r.value if isinstance(r, UserRole) else r for r in roles}

    def _dep(current: User = Depends(get_current_user)) -> User:
        if current.role.value not in allowed:
            raise AppError("forbidden", "Insufficient role for this action.", 403)
        return current

    return _dep
