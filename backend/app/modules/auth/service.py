"""Authentication service: credential check, login throttle, token issue.

Login throttling (D-V1-5) is Redis-only — no persistent lockout columns.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.users.models import User
from app.shared.errors import AppError

_MAX_FAILS = 5
_WINDOW_SECONDS = 15 * 60


def _fail_key(email: str, ip: str) -> str:
    return f"loginfail:{email.lower()}:{ip}"


def authenticate(db: Session, email: str, password: str, ip: str) -> tuple[str, int]:
    redis = get_redis()
    key = _fail_key(email, ip)

    if int(redis.get(key) or 0) >= _MAX_FAILS:
        raise AppError(
            "rate_limited", "Too many failed attempts. Try again later.", 429
        )

    user = db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    ).scalar_one_or_none()

    if user is None or not user.is_active or not verify_password(
        password, user.password_hash
    ):
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, _WINDOW_SECONDS)
        raise AppError("invalid_credentials", "Invalid email or password.", 401)

    redis.delete(key)
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    db.commit()

    return create_access_token(user_id=str(user.id), role=user.role.value)


def change_password(
    db: Session, user: User, current_password: str, new_password: str
) -> None:
    """Self-service password change.

    Verifies the caller's current password, enforces the existing policy via
    hash_password, and stores the new hash. The current session/token is kept
    active (no revocation) per Phase 2 requirements.
    """
    if not verify_password(current_password, user.password_hash):
        raise AppError("invalid_credentials", "Current password is incorrect.", 400)

    if verify_password(new_password, user.password_hash):
        raise AppError(
            "validation_error",
            "New password must be different from the current password.",
            422,
        )

    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise AppError("validation_error", str(exc), 422)

    db.add(user)
    db.commit()
