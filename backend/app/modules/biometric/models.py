"""Biometric ingestion ORM models (migration 0066).

Three additive tables. Nothing here touches `attendance_records` or any other
existing table - the only link to the rest of CoreOps is a nullable
`employee_id` on a punch, set when a mapping resolves.

  biometric_punches            immutable external event log (one row per punch)
  biometric_sync_batches       one row per connector ingestion attempt
  biometric_employee_mappings  external code -> CoreOps employee

`BiometricPunch` carries only `created_at` (no `updated_at`, no `deleted_at`),
mirroring `AuditLog`: a raw punch is a fact that happened, so it is never
updated and never deleted. A punch whose employee cannot be resolved is stored
with `employee_id = NULL` and resolved later, when a mapping is added - it is
never discarded, because a dropped punch is unrecoverable while an unmapped one
is merely pending.

Phase 2 stores punch state verbatim and derives nothing from it. There is no
IN/OUT column, no session, and no duration anywhere in this module.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.biometric.constants import (
    BATCH_PROCESSING,
    BATCH_STATUSES,
    MAX_BATCH_KEY_LEN,
    MAX_CONNECTOR_ID_LEN,
    MAX_EMPLOYEE_CODE_LEN,
    MAX_EXTERNAL_ID_LEN,
    MAX_SHORT_FIELD_LEN,
    MAX_STATE_FIELD_LEN,
)
from app.shared.base import TimestampMixin, UUIDMixin

_STATUS_LIST = ", ".join(f"'{s}'" for s in BATCH_STATUSES)

# Every timestamp here is declared timezone-aware EXPLICITLY (as
# attendance_records.check_in_at already is), not left to the bare
# `Mapped[datetime]` inference the shared mixins use. Without it SQLAlchemy
# emits `::TIMESTAMP WITHOUT TIME ZONE` casts and correctness would depend on
# the session TimeZone matching on the way in and out - not something an
# attendance record should rest on.
_TS = DateTime(timezone=True)


class BiometricSyncBatch(UUIDMixin, TimestampMixin, Base):
    """One connector ingestion attempt, with its outcome counters.

    `(provider, connector_id, batch_key)` is unique, which is what makes a
    retried POST resolve the SAME batch row instead of creating a second one.
    `error_message` is always a sanitized, operator-facing string - no token,
    no EasyTime credential, no raw exception text (see service._safe_error).
    """

    __tablename__ = "biometric_sync_batches"

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    connector_id: Mapped[str] = mapped_column(String(MAX_CONNECTOR_ID_LEN), nullable=False)
    batch_key: Mapped[str] = mapped_column(String(MAX_BATCH_KEY_LEN), nullable=False)

    # The EasyTime query window this batch covers, as reported by the connector.
    # Nullable because a manual/backfill push may not have a meaningful window.
    source_from_time: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    source_to_time: Mapped[datetime | None] = mapped_column(_TS, nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        _TS, server_default=text("now()"), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)

    records_received: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    records_inserted: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    records_duplicates: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    records_unmapped: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    records_invalid: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, server_default=text(f"'{BATCH_PROCESSING}'")
    )
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # Idempotency anchor for the batch record itself: re-POSTing the same
        # batch_key resolves this row rather than inserting a second attempt.
        UniqueConstraint(
            "provider",
            "connector_id",
            "batch_key",
            name="biometric_sync_batches_key_uq",
        ),
        CheckConstraint(
            f"status IN ({_STATUS_LIST})",
            name="biometric_sync_batches_status_valid",
        ),
        CheckConstraint(
            "records_received >= 0 AND records_inserted >= 0 "
            "AND records_duplicates >= 0 AND records_unmapped >= 0 "
            "AND records_invalid >= 0",
            name="biometric_sync_batches_counts_nonneg",
        ),
        # Operations view: "the last N sync attempts", newest first.
        Index("biometric_sync_batches_started_idx", "started_at"),
    )


class BiometricPunch(UUIDMixin, Base):
    """One raw biometric transaction, exactly as the device recorded it.

    Immutable: no service in CoreOps updates or deletes a row here. Late-arriving
    punches simply insert later - `upload_time` records when EasyTime received
    the record, `punch_time` when the person actually punched, and the two must
    never be conflated. Because nothing is derived at write time, a future phase
    can recalculate any day from these rows after late punches land.
    """

    __tablename__ = "biometric_punches"

    created_at: Mapped[datetime] = mapped_column(
        _TS, server_default=text("now()"), nullable=False
    )

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    # Vendor primary key. Kept as text: it is an opaque identifier, and some
    # ZKTeco builds emit non-numeric ids.
    external_transaction_id: Mapped[str] = mapped_column(
        String(MAX_EXTERNAL_ID_LEN), nullable=False
    )
    # The code as the DEVICE knows it (EasyTime emitted plain numerics such as
    # "61" in the live probe). Always retained, even when it resolves.
    external_employee_code: Mapped[str] = mapped_column(
        String(MAX_EMPLOYEE_CODE_LEN), nullable=False
    )
    # NULL when no mapping resolved. SET NULL on employee delete so a purged
    # employee never destroys the punch history.
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
    )

    punch_time: Mapped[datetime] = mapped_column(_TS, nullable=False)
    upload_time: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        _TS, server_default=text("now()"), nullable=False
    )

    # Vendor state code, verbatim. NOT an IN/OUT flag - see constants.py.
    raw_punch_state: Mapped[str | None] = mapped_column(
        String(MAX_STATE_FIELD_LEN), nullable=True
    )
    punch_state_display: Mapped[str | None] = mapped_column(
        String(MAX_STATE_FIELD_LEN), nullable=True
    )
    terminal_alias: Mapped[str | None] = mapped_column(
        String(MAX_SHORT_FIELD_LEN), nullable=True
    )
    terminal_serial_number: Mapped[str | None] = mapped_column(
        String(MAX_SHORT_FIELD_LEN), nullable=True
    )
    verification_type: Mapped[str | None] = mapped_column(
        String(MAX_STATE_FIELD_LEN), nullable=True
    )
    source: Mapped[str | None] = mapped_column(
        String(MAX_STATE_FIELD_LEN), nullable=True
    )

    # Provenance. SET NULL rather than CASCADE: losing the batch must never
    # delete the punches it carried.
    sync_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("biometric_sync_batches.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Sanitized vendor payload (PII and secret-shaped keys stripped, size
    # capped) plus the original timestamp text under the reserved `_*_text` keys.
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        # THE idempotency guarantee. Duplicate protection is this database
        # constraint, not an application-side pre-check, so concurrent
        # connectors replaying the same window cannot both win.
        UniqueConstraint(
            "provider",
            "external_transaction_id",
            name="biometric_punches_provider_txn_uq",
        ),
        # Per-employee timeline: the Phase 3+ session builder's only read shape.
        Index("biometric_punches_employee_time_idx", "employee_id", "punch_time"),
        # The same timeline for punches that never mapped - the operations view
        # used to decide which mapping to create.
        Index(
            "biometric_punches_ext_code_time_idx",
            "external_employee_code",
            "punch_time",
        ),
        # Date-range sweeps and recalculation. Not served by the composite above
        # because employee_id leads it (and is nullable).
        Index("biometric_punches_punch_time_idx", "punch_time"),
        # "What arrived late?" - the query that drives recalculation once
        # yesterday's final punches are uploaded this morning.
        Index("biometric_punches_upload_time_idx", "upload_time"),
        # Batch provenance: what exactly did batch X land. Also keeps the
        # ON DELETE SET NULL check off a sequential scan.
        Index("biometric_punches_batch_idx", "sync_batch_id"),
    )


class BiometricEmployeeMapping(UUIDMixin, TimestampMixin, Base):
    """Explicit external-code -> CoreOps employee mapping.

    Needed because the live probe returned bare numeric EasyTime codes ("61")
    while CoreOps uses prefixed codes ("EMP225"), so the two are NOT assumed
    equal. Mappings are only ever created deliberately, never inferred from a
    name.

    A partial unique index enforces at most ONE ACTIVE mapping per
    (provider, external_employee_code), so an external code can never point at
    two employees at once, while superseded rows stay for history.
    """

    __tablename__ = "biometric_employee_mappings"

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    external_employee_code: Mapped[str] = mapped_column(
        String(MAX_EMPLOYEE_CODE_LEN), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # Who confirmed this pairing against the EasyTime UI, and when.
    verified_at: Mapped[datetime | None] = mapped_column(_TS, nullable=True)
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    __table_args__ = (
        # One ACTIVE mapping per external code. Partial, so deactivated history
        # rows for the same code coexist.
        Index(
            "biometric_employee_mappings_active_uq",
            "provider",
            "external_employee_code",
            unique=True,
            postgresql_where=text("is_active"),
        ),
        # "Which external codes point at this employee?"
        Index("biometric_employee_mappings_employee_idx", "employee_id"),
    )
