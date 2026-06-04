"""ActivityType ORM model — master reference for work report activity classification."""
import uuid

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin

CATEGORY_GENERAL = "GENERAL"
CATEGORY_PROJECT = "PROJECT"
CATEGORY_TAG_ESTIMATION = "TAG_ESTIMATION"

VALID_CATEGORIES = {CATEGORY_GENERAL, CATEGORY_PROJECT, CATEGORY_TAG_ESTIMATION}


class ActivityType(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "activity_types"

    code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=CATEGORY_GENERAL
    )
    requires_project: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index(
            "activity_types_code_uq",
            "code",
            unique=True,
            postgresql_where=text("is_active = true AND code IS NOT NULL"),
        ),
        Index("activity_types_category_idx", "category"),
        Index("activity_types_active_idx", "is_active"),
    )
