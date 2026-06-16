from datetime import datetime
from typing import Literal, Optional
import uuid

from pydantic import BaseModel

Severity = Literal["INFO", "WARNING", "CRITICAL"]


class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: str
    severity: Severity
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    target_url: Optional[str]
    is_read: bool
    resolved_at: Optional[datetime]
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int


class UnreadCountOut(BaseModel):
    count: int
