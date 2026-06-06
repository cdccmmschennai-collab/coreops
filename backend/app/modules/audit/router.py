"""Audit log endpoints (project_manager only).

  GET /audit-logs          paginated, filterable audit trail
  GET /audit-logs/{id}     single audit entry

Read-only by design — there is no create/update/delete endpoint. Audit rows are
written internally by other services via audit.service.record_audit.
"""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.modules.audit import service
from app.modules.audit.models import AuditLog
from app.modules.audit.schemas import AuditLogOut, AuditLogPage
from app.modules.users.models import User
from app.shared.errors import AppError

router = APIRouter(prefix="/audit-logs", tags=["audit"])

AdminUser = Depends(require_role("project_manager"))


@router.get("", response_model=AuditLogPage)
def list_audit_logs(
    actor_user_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> AuditLogPage:
    rows, total = service.list_audit_logs(
        db,
        actor_user_id=actor_user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return AuditLogPage(
        items=[AuditLogOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{log_id}", response_model=AuditLogOut)
def get_audit_log(
    log_id: uuid.UUID,
    _admin: User = AdminUser,
    db: Session = Depends(get_db),
) -> AuditLogOut:
    entry = db.get(AuditLog, log_id)
    if entry is None:
        raise AppError("not_found", "Audit log entry not found.", 404)
    return AuditLogOut.model_validate(entry)
