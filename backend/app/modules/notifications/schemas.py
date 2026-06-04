from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    type: str
    title: str
    message: str
    entity_type: Optional[str]
    entity_id: Optional[uuid.UUID]
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    total: int
    limit: int
    offset: int


class UnreadCountOut(BaseModel):
    count: int
