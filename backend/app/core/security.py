"""Security utilities: password hashing, JWT, token revocation.

Decisions (V1_AUTHENTICATION_PLAN.md):
  D-V1-1  bcrypt directly (no passlib)
  D-V1-2  JWT HS256 with SECRET_KEY
  D-V1-4  logout via Redis denylist keyed on the token `jti`
"""
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import settings
from app.core.redis import get_redis

_BCRYPT_ROUNDS = 12
_MAX_PASSWORD_BYTES = 72  # bcrypt hard limit
_ALGORITHM = "HS256"
_DENY_PREFIX = "denylist:"


class TokenError(Exception):
    """Raised when a JWT is invalid, expired, or tampered with."""


# ---------- Password hashing ----------------------------------------------
def hash_password(raw: str) -> str:
    pw = raw.encode("utf-8")
    if len(pw) > _MAX_PASSWORD_BYTES:
        raise ValueError("Password cannot be longer than 72 bytes.")
    return bcrypt.hashpw(pw, bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------- JWT ------------------------------------------------------------
def create_access_token(*, user_id: str, role: str) -> tuple[str, int]:
    """Return (token, expires_in_seconds)."""
    now = datetime.now(timezone.utc)
    expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    payload = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=_ALGORITHM)
    return token, expires_in


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:  # expired, bad signature, malformed
        raise TokenError(str(exc)) from exc


# ---------- Token revocation (logout denylist) -----------------------------
def revoke_token(jti: str, exp_ts: int) -> None:
    """Denylist a token id until its natural expiry (self-cleaning key)."""
    ttl = max(1, exp_ts - int(datetime.now(timezone.utc).timestamp()))
    get_redis().setex(f"{_DENY_PREFIX}{jti}", ttl, "1")


def is_revoked(jti: str) -> bool:
    return get_redis().exists(f"{_DENY_PREFIX}{jti}") == 1
