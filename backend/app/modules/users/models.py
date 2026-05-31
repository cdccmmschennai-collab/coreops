"""User (identity) ORM model — v1 schema per V1_ARCHITECTURE_PACKAGE.md §3.

No persistent lockout/MFA columns in v1 (throttling is Redis-side).
"""
import enum
from datetime import datetime

from sqlalchemy import Boolean, Index, String, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import SoftDeleteMixin, TimestampMixin, UUIDMixin


class UserRole(str, enum.Enum):
    admin = "admin"
    manager = "manager"
    employee = "employee"
    viewer = "viewer"


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=UserRole.employee.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "users_email_uq",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )
