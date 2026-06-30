"""Authentication service: credential check, login throttle, token issue.

Login throttling (D-V1-5) is Redis-only — no persistent lockout columns.

Identifier-based login: the login field accepts an email, an employee_code, or
an employee first_name (resolved by `resolve_login_user`). Names are not unique,
so when a first_name matches more than one active account we return an
`ambiguous_identifier` response (409) listing the candidate accounts instead of
failing — the client re-submits with the chosen employee_code.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.audit import service as audit
from app.modules.audit.constants import AuditAction, EntityType, STATUS_FAILURE
from app.modules.employees.models import Employee
from app.modules.users.models import User
from app.shared.errors import AppError

_MAX_FAILS = 5
_WINDOW_SECONDS = 15 * 60


def _fail_key(identifier: str, ip: str) -> str:
    return f"loginfail:{identifier.strip().lower()}:{ip}"


@dataclass
class ResolvedLogin:
    """Outcome of mapping a login identifier to an account.

    - ``user`` set        → exactly one usable account matched.
    - ``candidates`` set  → a first_name matched 2+ usable accounts (ambiguous).
    - both empty          → no usable account matched.
    """

    user: User | None = None
    candidates: list[Employee] = field(default_factory=list)


def _usable_account_query():
    """Employees joined to a usable (active, non-deleted) login account."""
    return (
        select(Employee, User)
        .join(User, Employee.user_id == User.id)
        .where(
            Employee.deleted_at.is_(None),
            User.deleted_at.is_(None),
            User.is_active.is_(True),
        )
    )


def resolve_login_user(db: Session, identifier: str) -> ResolvedLogin:
    """Map a login identifier to an account.

    Priority: email (contains ``@``) → employee_code → first_name. Inactive,
    soft-deleted, and login-less employees are never matched. A first_name that
    matches multiple usable accounts yields candidates, never a single user.
    """
    ident = identifier.strip()
    if not ident:
        return ResolvedLogin()

    # (1) Email — only when it looks like one.
    if "@" in ident:
        user = db.execute(
            select(User).where(User.email == ident, User.deleted_at.is_(None))
        ).scalar_one_or_none()
        return ResolvedLogin(user=user if (user and user.is_active) else None)

    # (2) Employee code — unique, so at most one usable match.
    code_row = db.execute(
        _usable_account_query().where(
            func.lower(Employee.employee_code) == ident.lower()
        )
    ).first()
    if code_row is not None:
        return ResolvedLogin(user=code_row[1])

    # (3) First name — may match 0, 1, or many usable accounts.
    name_rows = db.execute(
        _usable_account_query().where(func.lower(Employee.first_name) == ident.lower())
    ).all()
    if len(name_rows) == 1:
        return ResolvedLogin(user=name_rows[0][1])
    if len(name_rows) >= 2:
        return ResolvedLogin(candidates=[emp for emp, _user in name_rows])
    return ResolvedLogin()


def _candidate_payload(candidates: list[Employee]) -> list[dict]:
    return [{"employee_code": e.employee_code, "name": e.full_name} for e in candidates]


def authenticate(db: Session, identifier: str, password: str, ip: str) -> tuple[str, int]:
    redis = get_redis()
    key = _fail_key(identifier, ip)

    if int(redis.get(key) or 0) >= _MAX_FAILS:
        audit.record_audit(
            db,
            action=AuditAction.LOGIN_RATE_LIMITED,
            actor_email=identifier,
            status=STATUS_FAILURE,
            details={"attempted_identifier": identifier},
            commit=True,
        )
        raise AppError(
            "rate_limited", "Too many failed attempts. Try again later.", 429
        )

    resolution = resolve_login_user(db, identifier)

    # Ambiguous first name → ask the client to pick an account. This is not a
    # credential failure, so it deliberately does NOT increment the throttle
    # counter (the legitimate owner would otherwise lock themselves out before
    # they could even select their account).
    if resolution.candidates:
        raise AppError(
            "ambiguous_identifier",
            "Multiple accounts match that name. Select your account to continue.",
            409,
            {"candidates": _candidate_payload(resolution.candidates)},
        )

    user = resolution.user
    if user is None or not verify_password(password, user.password_hash):
        count = redis.incr(key)
        if count == 1:
            redis.expire(key, _WINDOW_SECONDS)
        audit.record_audit(
            db,
            action=AuditAction.LOGIN_FAILURE,
            actor=user,
            actor_email=identifier,
            entity_type=EntityType.USER,
            entity_id=user.id if user is not None else None,
            status=STATUS_FAILURE,
            details={
                "attempted_identifier": identifier,
                "reason": "invalid_credentials",
            },
            commit=True,
        )
        raise AppError("invalid_credentials", "Invalid login or password.", 401)

    redis.delete(key)
    user.last_login_at = datetime.now(timezone.utc)
    db.add(user)
    audit.record_audit(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor=user,
        entity_type=EntityType.USER,
        entity_id=user.id,
    )
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
    audit.record_audit(
        db,
        action=AuditAction.PASSWORD_CHANGE_SELF,
        actor=user,
        entity_type=EntityType.USER,
        entity_id=user.id,
    )
    db.commit()
