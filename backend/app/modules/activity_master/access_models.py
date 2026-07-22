"""EmployeeActivityAccess ORM model — which employees may use a RESTRICTED
Activity (migration 0061).

Global (not project-scoped) employee-to-activity authorization: one row per
(activity, employee) grant. Access is soft-revoked, never hard-deleted, so the
grant/revoke history survives for audit:

  is_active = true   -> the employee may currently use the RESTRICTED activity
  is_active = false  -> access was revoked (revoked_by_id / revoked_at set)

Re-granting a previously revoked pair REACTIVATES the existing row (flips
is_active back to true, clears revoked_*, refreshes granted_*) rather than
inserting a duplicate — enforced both by the (activity_id, employee_id) unique
constraint and the service's upsert path.

activity_id references the top-level Activity (level='activity'); sub-activities
inherit their parent's access and never carry their own grants.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class EmployeeActivityAccess(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "employee_activity_access"

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_master.id", ondelete="CASCADE"),
        nullable=False,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # The PM (users.id) who granted the currently-active access. SET NULL so a
    # purged user never blocks the grant history.
    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    granted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # One row per (activity, employee): re-granting reactivates it in place.
        UniqueConstraint(
            "activity_id", "employee_id", name="employee_activity_access_pair_uq"
        ),
        # Active employees for one activity (the read-side assignment list +
        # the report-dropdown EXISTS check).
        Index(
            "employee_activity_access_activity_active_idx",
            "activity_id",
            "is_active",
        ),
        # "does THIS employee have access to THIS activity" + "all active
        # restricted activities for one employee" — the write-path bulk check.
        Index(
            "employee_activity_access_employee_activity_idx",
            "employee_id",
            "activity_id",
            "is_active",
        ),
    )
