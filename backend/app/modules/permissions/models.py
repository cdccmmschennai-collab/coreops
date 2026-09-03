"""Permission Request ORM model (Phase 11).

"Permission" is the attendance sense, NOT an RBAC capability: an hour or two of
sanctioned absence inside an otherwise normal working day. A permission day stays
`present` in `attendance_records` - the hours are a separate attribute, held here.

Status lifecycle (four states, no fifth):
  pending  -> approved | rejected | cancelled
  approved -> cancelled            (restores the hours)

Leave has a `cancellation_requested` state because an approved multi-day absence
stands until a manager rules on its withdrawal. One or two hours has nothing to
hold open, so cancellation here is a single step.

`manager_id` is the reviewer, captured at decision time (denormalised audit
column, exactly as `leave_requests.manager_id` is - the employee's manager may
change after the decision). `created_at` is the requested-at timestamp; there is
no second column for it.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.base import TimestampMixin, UUIDMixin


class PermissionStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"


class PermissionPeriod(str, enum.Enum):
    """The four selectable permission options (Phase 4C).

    This is the ONE authoritative value a requester picks - the approver never
    has to infer a half from `duration_hours` or any other column. `duration_hours`
    stays on the row too, but only as bookkeeping DERIVED from this at creation
    (see `PERIOD_HOURS` and `service.create_permission_request`): the balance sum,
    the DB check constraint and the attendance join all read hours, and rewriting
    every one of those to parse a period string is a bigger, riskier change than
    this phase asks for.

    Nullable on the row: a permission filed before this phase has no half on
    record and none can be inferred, so it stays `None` and falls back to a plain
    "N hour(s)" rendering - see `service._duration_label`.
    """

    first_half_1h = "first_half_1h"
    second_half_1h = "second_half_1h"
    first_half_2h = "first_half_2h"
    second_half_2h = "second_half_2h"


# How many hours each option costs. The only source of `duration_hours` for a
# NEW request - see `service.create_permission_request`.
PERIOD_HOURS: dict[PermissionPeriod, int] = {
    PermissionPeriod.first_half_1h: 1,
    PermissionPeriod.second_half_1h: 1,
    PermissionPeriod.first_half_2h: 2,
    PermissionPeriod.second_half_2h: 2,
}

# The exact wording the form, the detail page and the email all show. An em
# dash, not a hyphen, matching the label the product asked for verbatim.
PERIOD_LABELS: dict[PermissionPeriod, str] = {
    PermissionPeriod.first_half_1h: "1st Half — 1 Hour",
    PermissionPeriod.second_half_1h: "2nd Half — 1 Hour",
    PermissionPeriod.first_half_2h: "1st Half — 2 Hours",
    PermissionPeriod.second_half_2h: "2nd Half — 2 Hours",
}


def duration_label(duration_hours: int, period: PermissionPeriod | None) -> str:
    """The exact selected option, e.g. "1st Half — 1 Hour" - the ONE authoritative
    wording every surface (notification, email, detail page) uses. Falls back to
    a plain "N hour(s)" only for a request filed before Phase 4C, which has no
    period on record and none that could be safely guessed.
    """
    if period is not None:
        return PERIOD_LABELS[period]
    unit = "hour" if duration_hours == 1 else "hours"
    return f"{duration_hours} {unit}"


class PermissionRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permission_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    # A permission is always a single day. There is no range: two hours off on
    # Monday and one on Tuesday are two separate decisions with two separate
    # balances to check.
    permission_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Whole hours, 1 or 2 - enforced by the check constraint below as well as by
    # the API schema, so no script or fixture can create a 30-minute permission.
    # For a request created since Phase 4C this is DERIVED from `period` via
    # `PERIOD_HOURS`, never chosen independently - see `service.
    # create_permission_request`.
    duration_hours: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # The actual selected option (Phase 4C) - one of the four `PermissionPeriod`
    # values, e.g. "1st Half - 1 Hour". NULL on every row created before this
    # phase, which had no half to record; those keep displaying as a plain
    # "N hour(s)" (see `service._duration_label`). This is the one field a
    # reviewer or an email reads to know what was actually asked for - never
    # inferred from `duration_hours` alone.
    period: Mapped[PermissionPeriod | None] = mapped_column(
        SAEnum(
            PermissionPeriod,
            name="permission_period",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[PermissionStatus] = mapped_column(
        SAEnum(
            PermissionStatus,
            name="permission_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        server_default=text("'pending'"),
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The project the employee's latest valid Daily Work Report evidence shows
    # them on, resolved once at creation (Phase 4B) by the SAME resolver Leave
    # uses - leave/routing.py::resolve_routed_project. Historical only, never a
    # frozen approver: who reviews is always the project's CURRENT
    # head_employee_id, looked up fresh via app.core.authz at read/review time.
    # NULL means no single project could be determined and the request falls
    # back to the existing PM / reporting_pm_id approval flow.
    routed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("duration_hours IN (1, 2)", name="permission_duration_1h_or_2h"),
        Index("permission_employee_date_idx", "employee_id", "permission_date"),
        Index("permission_status_idx", "status"),
        Index("permission_manager_idx", "manager_id", "status"),
        Index("permission_routed_project_idx", "routed_project_id"),
    )
