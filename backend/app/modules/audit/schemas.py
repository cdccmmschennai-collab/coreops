"""Audit log API schemas."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    actor_user_id: Optional[uuid.UUID]
    actor_email: Optional[str]
    actor_role: Optional[str]
    action: str
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    status: str
    ip_address: Optional[str]
    user_agent: Optional[str]
    details: dict

    model_config = {"from_attributes": True}


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int
    limit: int
    offset: int
