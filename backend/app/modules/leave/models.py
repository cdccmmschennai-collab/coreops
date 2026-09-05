"""Leave Request ORM model.

Status lifecycle:
  pending  → approved | rejected | cancelled
  approved → cancellation_requested → cancelled | approved

manager_id is captured at decision time (denormalised audit column — the
requesting employee's manager may change after approval).
"""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
# Pure and dependency-free (it imports `enum` and nothing else), so composing the
# Type a reader sees out of BOTH facts can live beside the half-day wording it
# needs rather than being re-derived at each display site. One-directional:
# `classification.py` knows nothing about this module.
from app.modules.leave.classification import (
    LeaveClassification,
    classification_label,
)
from app.shared.base import TimestampMixin, UUIDMixin


class LeaveType(str, enum.Enum):
    """RETIRED. The leave categories CoreOps used before Normal/Special.

    Nobody chooses one of these any more: a request's classification is derived
    from its authoritative working-day count by `leave/classification.py`, and
    that is the only classification the API accepts or exposes.

    The enum and its column survive - unchanged, and with no migration - for one
    reason: `unpaid` still means "the pool does not pay for this absence" to
    `effects.BALANCE_DEDUCTING_TYPES` and `leave_balances/ledger.py`. Rewriting
    the historical rows would silently restate past leave balances, so the
    stored values are left exactly as they were filed and simply stopped being
    read as a classification.
    """

    casual = "casual"
    sick = "sick"
    annual = "annual"
    comp_off = "comp_off"
    unpaid = "unpaid"
    other = "other"


# What a NEW request stores in the retired column, which is NOT NULL. `other`
# is the neutral member: it deducts from the pool exactly as `casual`, `annual`
# and `comp_off` did, so every request filed from here on behaves precisely as
# a request filed yesterday. The value is never read back as a classification.
RETIRED_LEAVE_TYPE = LeaveType.other


class LeaveHalfDayPeriod(str, enum.Enum):
    """WHICH HALF of a single working day a half-day leave covers.

    Two variants of ONE action, not two actions: both are a half-day leave, both
    cost exactly `HALF_DAY_LEAVE_FRACTION`, and both travel the identical
    request -> routing -> Head -> approval -> notification -> attendance path a
    full-day leave travels. The half exists so the record says WHICH portion of
    the day was leave; nothing downstream branches on it.

    NULL on the row - the enum's absence - is the ordinary full-day leave every
    request in this table was before migration 0084, so the default reading of
    an existing row is unchanged.

    The member NAMES are never shown to anybody. `HALF_DAY_PERIOD_LABELS` below
    is the only wording a person sees.
    """

    first_half = "first_half"
    second_half = "second_half"


# What one half-day leave costs the leave pool, written onto the attendance
# record as `leave_day_fraction` (migration 0083) by `effects.apply_leave_approved`.
#
# BOTH VARIANTS, EXACTLY. A half day is half a day whichever half of it was
# taken, so there is one constant and no per-variant table: an arbitrary
# fraction cannot be introduced by choosing a different half.
HALF_DAY_LEAVE_FRACTION = Decimal("0.5")

# The exact user-facing wording for each variant, and the ONLY wording either
# variant is ever shown as. The technical member names (`first_half`,
# `second_half`) and the word HALF_DAY never reach a screen or an email.
#
# PRODUCT-FIXED WORDING. These two strings are the ones the Leave Request
# dropdown offers, character for character; they are not a house style this
# module gets to restyle. Phase 1 shipped "Half Day · 1st Half" / "· 2nd Half"
# and Phase 2 replaced both - so no dot separator, no "1st"/"2nd", and (as
# always across CoreOps) no em or en dash. Mirror this map in
# `frontend/src/features/leave/types.ts::LEAVE_HALF_DAY_LABEL` if either is ever
# touched: the form and the backend must not be able to disagree about what the
# employee picked.
HALF_DAY_PERIOD_LABELS: dict[LeaveHalfDayPeriod, str] = {
    LeaveHalfDayPeriod.first_half: "Half Day (First)",
    LeaveHalfDayPeriod.second_half: "Half Day (Second)",
}


def half_day_period_label(period: LeaveHalfDayPeriod | None) -> str | None:
    """The user-facing name of a half-day variant, or None for a full-day leave.

    None rather than a placeholder: a request with no half is not a half-day
    leave at all, and its Type is the Normal/Special classification the caller
    already has. See `classification.classification_label`.
    """
    return HALF_DAY_PERIOD_LABELS.get(period) if period is not None else None


# What a half-day leave's DURATION reads as, everywhere a duration is shown.
# One string, because both variants cost `HALF_DAY_LEAVE_FRACTION` exactly - the
# same reason there is one fraction and not a per-variant table. Singular "day"
# on purpose: half of one day is not "0.5 days".
HALF_DAY_DURATION_LABEL = "0.5 day"


def leave_type_label(
    classification: LeaveClassification,
    period: LeaveHalfDayPeriod | None,
) -> str:
    """THE TYPE A READER SEES, composed from both facts in one place.

    THE DISPLAY PRECEDENCE, and the whole of it::

        half_day_period == first_half   ->  "Half Day (First)"
        half_day_period == second_half  ->  "Half Day (Second)"
        otherwise                       ->  the Normal/Special label, unchanged

    A half-day request has a `classification` too - one working day is <= 3, so
    it classifies Normal - and that is precisely the bug this composer exists to
    stop: every Type surface read `classification` alone, so a half day was
    displayed, listed and emailed as "Normal". The half is the more specific
    fact, so it wins; nothing about Normal/Special changes for the requests that
    do not have one.

    The half's wording comes from `HALF_DAY_PERIOD_LABELS` and the full-day
    wording from `classification.CLASSIFICATION_LABELS`, so neither is respelled
    here and neither can drift from the form the employee chose in.
    """
    half = half_day_period_label(period)
    return half if half is not None else classification_label(classification)


def leave_duration_label(
    working_days: int, period: LeaveHalfDayPeriod | None
) -> str:
    """`0.5 day` for a half-day leave, otherwise the working-day count.

    The count comes from `effects.leave_working_days` for every full-day
    request, exactly as before - this only intercepts the one case where that
    count is misleading. A half-day request covers one working day, so the
    honest count is 1 and the honest DURATION is half of it; showing "1 day"
    against a request the employee filed as half a day is what the reader
    reported as wrong.

    Phase 3 is what makes the leave pool agree with this line
    (`HALF_DAY_LEAVE_FRACTION` on the attendance record); nothing here prices
    anything.
    """
    if period is not None:
        return HALF_DAY_DURATION_LABEL
    return f"{working_days} {'day' if working_days == 1 else 'days'}"


class LeaveStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"
    cancelled = "cancelled"
    # Approved leave the employee has asked to withdraw. The absence still
    # stands until a project manager decides, so this counts as active leave.
    cancellation_requested = "cancellation_requested"


class LeaveRequest(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "leave_requests"

    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    leave_type: Mapped[LeaveType] = mapped_column(
        SAEnum(LeaveType, name="leave_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    # WHICH HALF of the day this leave covers, when it covers only half of one
    # (migration 0084). NULL is an ordinary full-day leave, which is what every
    # request filed before that migration is and what every request that does
    # not choose a half still is.
    #
    # This is the one field that distinguishes a half-day leave, and it is the
    # only thing this feature adds to the request: routing, the Project Head,
    # the approval, the notifications and the audit trail all read exactly what
    # they read for a full-day leave. `effects.apply_leave_approved` is the
    # single place it changes anything - it writes `half_day` +
    # `HALF_DAY_LEAVE_FRACTION` instead of `leave` on the attendance record, and
    # `leave_balances.ledger.leave_days_for` then prices that row at 0.5 with no
    # rule of its own for half-day leave.
    half_day_period: Mapped["LeaveHalfDayPeriod | None"] = mapped_column(
        SAEnum(
            LeaveHalfDayPeriod,
            name="leave_half_day_period",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeaveStatus] = mapped_column(
        SAEnum(LeaveStatus, name="leave_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        server_default=text("'pending'"),
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="SET NULL"), nullable=True
    )
    manager_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The project the employee's PREVIOUS WORKING DAY's Daily Work Report shows
    # them on, resolved once at creation by leave/routing.py. This is the
    # historical PROJECT only — never a frozen head id. Who may review/is
    # notified is always the project's CURRENT head_employee_id, looked up
    # fresh via app.core.authz at read/notify/approve time, so a Head
    # reassignment after this request was filed is honoured (Phase 1 spec §15).
    # NULL means no single project could be determined - the request falls
    # back to the existing PM approval flow.
    routed_project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="leave_dates_order"),
        # A half day is half of ONE day. The floor under the API validation, so
        # nothing outside the API can create a "half day" spanning a range -
        # which would owe 0.5 to each of its working days and break the rule
        # that both variants consume exactly one half day.
        CheckConstraint(
            "half_day_period IS NULL OR start_date = end_date",
            name="leave_half_day_is_one_day",
        ),
        Index("leave_employee_idx", "employee_id", "start_date"),
        Index("leave_manager_idx", "manager_id", "status"),
        Index("leave_status_idx", "status"),
        Index("leave_routed_project_idx", "routed_project_id"),
    )
