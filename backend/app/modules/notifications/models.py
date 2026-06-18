"""Notification ORM model — one row per (user, workflow event).

Most notifications (report submitted/rejected/edit-granted, etc.) are one-off
events created via `create_notification` and never revisited. Ongoing
*conditions* (a NUMERIC benchmark shortfall, an overdue TASK_BASED activity)
instead get a single persistent row per (user_id, entity_type, entity_id,
type) via `upsert_notification` — updated in place rather than re-inserted
every time the condition is re-checked, and stamped `resolved_at` the moment
it clears (`resolve_notification`). De-dup is enforced in the service layer,
not a DB constraint, to keep this additive/simple.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import UUIDMixin

SEVERITY_INFO = "INFO"
SEVERITY_WARNING = "WARNING"
SEVERITY_CRITICAL = "CRITICAL"
VALID_SEVERITIES = {SEVERITY_INFO, SEVERITY_WARNING, SEVERITY_CRITICAL}


class Notification(UUIDMixin, Base):
    __tablename__ = "notifications"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, server_default=SEVERITY_INFO)
    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    target_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_read: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # NULL = still an active/unresolved condition. Irrelevant for one-off
    # event notifications, which are never "resolved", just read.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'CRITICAL')",
            name="notifications_severity_valid",
        ),
    )
