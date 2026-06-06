"""Audit logging service.

`record_audit` is called from inside other services at the point of a
security-sensitive mutation. By default it joins the caller's transaction
(`db.flush()` only) so the audit row commits atomically with the change it
describes. For events that occur on an exception path which will roll back the
session (e.g. a failed login before the caller raises), pass `commit=True` so
the audit row is persisted in its own transaction first.

There is intentionally no update or delete path: audit rows are immutable.
"""
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.context import get_request_ip, get_request_user_agent
from app.modules.audit.constants import STATUS_SUCCESS
from app.modules.audit.models import AuditLog
from app.modules.users.models import User


def record_audit(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    status: str = STATUS_SUCCESS,
    details: dict | None = None,
    commit: bool = False,
) -> AuditLog:
    """Append one audit row.

    Actor identity is snapshotted from `actor` when given; `actor_email` /
    `actor_role` overrides are used for events without a resolved User (e.g. a
    failed login where the email is known but the user may not exist). Client
    IP / user-agent are read from the per-request ContextVars.
    """
    entry = AuditLog(
        actor_user_id=actor.id if actor is not None else None,
        actor_email=actor_email if actor_email is not None else (actor.email if actor else None),
        actor_role=actor_role if actor_role is not None else (actor.role.value if actor else None),
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        ip_address=get_request_ip(),
        user_agent=get_request_user_agent(),
        details=details or {},
    )
    db.add(entry)
    if commit:
        db.commit()
        db.refresh(entry)
    else:
        db.flush()
    return entry


def list_audit_logs(
    db: Session,
    *,
    actor_user_id: uuid.UUID | None = None,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    status: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int,
    offset: int,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    if actor_user_id is not None:
        stmt = stmt.where(AuditLog.actor_user_id == actor_user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if status:
        stmt = stmt.where(AuditLog.status == status)
    if date_from is not None:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to is not None:
        stmt = stmt.where(AuditLog.created_at <= date_to)

    total = db.execute(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ).scalar_one()
    rows = (
        db.execute(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), total
