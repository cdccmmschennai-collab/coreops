"""Activity access-control pydantic schemas (migration 0061)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AccessType = Literal["COMMON", "RESTRICTED"]


class AuthorizedEmployeeOut(BaseModel):
    """One active grant on a RESTRICTED activity. Deliberately minimal — no
    email / phone / department; the PM only needs to identify who can use it."""

    model_config = ConfigDict(from_attributes=True)

    employee_id: uuid.UUID
    employee_code: str
    employee_name: str
    granted_by: str | None
    granted_at: datetime | None


class ActivityAccessConfigOut(BaseModel):
    activity_id: uuid.UUID
    access_type: AccessType
    authorized_count: int
    items: list[AuthorizedEmployeeOut]
    total: int
    limit: int
    offset: int


class ChangeAccessTypeIn(BaseModel):
    """PATCH .../access-type. COMMON->RESTRICTED must carry at least one employee
    (validated in the service, atomically with the type flip)."""

    access_type: AccessType
    employee_ids: list[uuid.UUID] = Field(default_factory=list)


class GrantAccessIn(BaseModel):
    """POST .../access — bulk grant on an already-RESTRICTED activity."""

    employee_ids: list[uuid.UUID] = Field(min_length=1)


class GrantResultOut(BaseModel):
    """Summary of a bulk grant / access-type change."""

    activity_id: uuid.UUID
    access_type: AccessType
    granted: int
    reactivated: int
    already_active: int
    authorized_count: int
