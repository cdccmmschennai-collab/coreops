"""Employee pydantic schemas (match openapi-v1.yaml employees section)."""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.employees.models import EmployeeStatus
from app.modules.users.models import UserRole

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class EmployeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID | None = None
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    work_email: str | None = None
    personal_email: str | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    manager_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    status: EmployeeStatus
    created_at: datetime


class EmployeeCreate(BaseModel):
    employee_code: str = Field(min_length=1)
    first_name: str = Field(min_length=1)
    last_name: str = Field(min_length=1)
    user_id: uuid.UUID | None = None
    work_email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    personal_email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    manager_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    status: EmployeeStatus = EmployeeStatus.active


class EmployeeUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1)
    last_name: str | None = Field(default=None, min_length=1)
    work_email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    personal_email: str | None = Field(default=None, pattern=EMAIL_PATTERN)
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    manager_id: uuid.UUID | None = None
    office_id: uuid.UUID | None = None
    date_of_joining: date | None = None
    status: EmployeeStatus | None = None


class EmployeePage(BaseModel):
    items: list[EmployeeOut]
    total: int
    limit: int
    offset: int


# ---------- account management ----------

class AccountCreate(BaseModel):
    """Create a new login account and link it to the employee."""
    email: str = Field(pattern=EMAIL_PATTERN)
    password: str = Field(min_length=8)
    role: UserRole = UserRole.employee


class AccountPasswordReset(BaseModel):
    new_password: str = Field(min_length=8)


class AccountStatusUpdate(BaseModel):
    is_active: bool


# ---------- self-service profile ----------

class EmployeeProfile(BaseModel):
    """Business-identity view embedded in /auth/me.

    Manager and office are resolved to display names server-side so that an
    employee (who may not read other employee/office rows) still sees them.
    """
    id: uuid.UUID
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    work_email: str | None = None
    personal_email: str | None = None
    phone: str | None = None
    department: str | None = None
    designation: str | None = None
    manager_id: uuid.UUID | None = None
    manager_name: str | None = None
    office_id: uuid.UUID | None = None
    office_name: str | None = None
    date_of_joining: date | None = None
    status: EmployeeStatus
