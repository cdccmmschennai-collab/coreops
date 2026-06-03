"""Employee ORM model — v1 schema per V1_ARCHITECTURE_PACKAGE.md §3.

Org structure (department/designation) is folded into columns; manager_id is a
self-FK enabling team scoping and (later) the org hierarchy.
"""
import enum
import uuid
from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class EmployeeStatus(str, enum.Enum):
    active = "active"
    on_leave = "on_leave"
    exited = "exited"


class Employee(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "employees"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    employee_code: Mapped[str] = mapped_column(Text, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    last_name: Mapped[str] = mapped_column(Text, nullable=False)
    work_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str | None] = mapped_column(Text, nullable=True)
    designation: Mapped[str | None] = mapped_column(Text, nullable=True)
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=True
    )
    office_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offices.id", ondelete="SET NULL"), nullable=True
    )
    date_of_joining: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[EmployeeStatus] = mapped_column(
        SAEnum(
            EmployeeStatus,
            name="employee_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=EmployeeStatus.active.value,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "manager_id IS NULL OR manager_id <> id", name="employees_no_self_manager"
        ),
        Index(
            "employees_code_uq",
            "employee_code",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "employees_work_email_uq",
            "work_email",
            unique=True,
            postgresql_where=text("work_email IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index(
            "employees_user_id_uq",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL AND deleted_at IS NULL"),
        ),
        Index("employees_manager_idx", "manager_id", postgresql_where=text("deleted_at IS NULL")),
        Index("employees_office_idx", "office_id", postgresql_where=text("deleted_at IS NULL")),
        Index("employees_status_idx", "status", postgresql_where=text("deleted_at IS NULL")),
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()
