"""JobCode ORM model — master reference for J-code / project billing codes."""
import uuid

from sqlalchemy import Boolean, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class JobCode(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "job_codes"

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index(
            "job_codes_code_uq",
            "code",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
        Index("job_codes_active_idx", "is_active"),
    )
