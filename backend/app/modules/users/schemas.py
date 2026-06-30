"""User & auth pydantic schemas (match openapi-v1.yaml).

Email is validated by regex pattern to avoid the `email-validator` dependency
while still enforcing a sane shape (the DB also CHECKs the format).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.employees.schemas import EmployeeProfile
from app.modules.users.models import UserRole

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


# ---------- Auth ----------
class LoginRequest(BaseModel):
    # Identifier may be an email, an employee_code, or an employee first_name —
    # resolved server-side. No format validation here beyond non-empty.
    identifier: str = Field(min_length=1)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChangePasswordRequest(BaseModel):
    """Self-service password change. Confirm-new is validated client-side."""
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)


# ---------- User ----------
class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: UserRole
    is_active: bool
    last_login_at: datetime | None = None
    created_at: datetime


class UserCreate(BaseModel):
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8)
    role: UserRole


class UserUpdate(BaseModel):
    is_active: bool | None = None
    role: UserRole | None = None


class RoleUpdate(BaseModel):
    role: UserRole


class PasswordUpdate(BaseModel):
    new_password: str = Field(min_length=8)


class LinkedEmployee(BaseModel):
    """Compact employee summary attached to a user row in the admin list."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    employee_code: str


class UserListItem(UserOut):
    """A user row enriched with its linked employee (one-to-one), if any."""
    linked_employee: LinkedEmployee | None = None


class UserPage(BaseModel):
    items: list[UserListItem]
    total: int
    limit: int
    offset: int


class Me(BaseModel):
    user: UserOut
    employee: EmployeeProfile | None = None  # linked business identity, if any
    employee_id: uuid.UUID | None = None  # linked employee profile id, if any
