"""0063 biometric punch ingestion (EasyTime Phase 2)

Purely additive: three NEW tables and nothing else. No existing table, column,
enum, index or constraint is altered or dropped. In particular
`attendance_records`, `leave_requests`, `daily_work_reports` and every export
path are untouched, so applying this migration cannot change a single number
any current screen or workbook shows.

1. biometric_sync_batches - one row per connector ingestion attempt, with its
   outcome counters and a sanitized error. UNIQUE(provider, connector_id,
   batch_key) is what makes a retried POST resolve the SAME attempt row instead
   of opening a second one. `status` is VARCHAR + CHECK rather than a new
   Postgres enum, following the benchmark_type / report_mode / access_type
   precedent - one fewer type to migrate when a status is added.

2. biometric_punches - the immutable raw event log. One row per device
   transaction, stored verbatim. The table carries created_at but deliberately
   NO updated_at and NO deleted_at (mirroring audit_logs): a punch is a fact,
   never edited, never removed.

   UNIQUE(provider, external_transaction_id) is the whole idempotency story.
   Ingestion inserts with ON CONFLICT DO NOTHING, so a connector replaying an
   overlap window - or two connectors racing on the same window - can never
   create a second row for one transaction, and the loser's genuinely-new
   punches in the same statement still land.

   employee_id is NULLABLE on purpose. An EasyTime code with no mapping yet
   stores the punch with employee_id = NULL rather than dropping it: a dropped
   punch is gone forever, an unmapped one is merely pending a mapping.

   Both employee FKs are ON DELETE SET NULL so purging an employee can never
   cascade away attendance evidence.

3. biometric_employee_mappings - external code -> CoreOps employee. The live
   probe returned bare numeric EasyTime codes ("61") while CoreOps uses prefixed
   codes ("EMP225"), so equality is NOT assumed. A PARTIAL unique index
   (WHERE is_active) allows superseded history rows to coexist while
   guaranteeing one external code can point at only one employee at a time.

Nothing here encodes punch-state meaning. `raw_punch_state` is plain text; the
live probe observed "0" on every punch with a null display label, and IN/OUT
stays unresolved (docs/attendance/punch-state-mapping.md).

Downgrade drops only these three new tables, in FK-safe order. It reads and
modifies no pre-existing row.

Revision ID: 0063_biometric_punch_ingestion
Revises: 0062_leave_cancellation_status
Create Date: 2026-07-30
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0063_biometric_punch_ingestion"
down_revision: Union[str, None] = "0062_leave_cancellation_status"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. biometric_sync_batches (created first: biometric_punches references it)
    op.create_table(
        "biometric_sync_batches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("connector_id", sa.String(100), nullable=False),
        sa.Column("batch_key", sa.String(128), nullable=False),
        sa.Column("source_from_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_to_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "records_received", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "records_inserted", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "records_duplicates",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "records_unmapped", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "records_invalid", sa.Integer(), nullable=False, server_default=sa.text("0")
        ),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'processing'"),
        ),
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "provider",
            "connector_id",
            "batch_key",
            name="biometric_sync_batches_key_uq",
        ),
        sa.CheckConstraint(
            "status IN ('processing', 'completed', 'completed_with_errors', 'failed')",
            name="biometric_sync_batches_status_valid",
        ),
        sa.CheckConstraint(
            "records_received >= 0 AND records_inserted >= 0 "
            "AND records_duplicates >= 0 AND records_unmapped >= 0 "
            "AND records_invalid >= 0",
            name="biometric_sync_batches_counts_nonneg",
        ),
    )
    op.create_index(
        "biometric_sync_batches_started_idx", "biometric_sync_batches", ["started_at"]
    )

    # 2. biometric_punches - immutable raw event log.
    op.create_table(
        "biometric_punches",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("external_transaction_id", sa.String(128), nullable=False),
        sa.Column("external_employee_code", sa.String(64), nullable=False),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("punch_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("upload_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("raw_punch_state", sa.String(50), nullable=True),
        sa.Column("punch_state_display", sa.String(50), nullable=True),
        sa.Column("terminal_alias", sa.String(100), nullable=True),
        sa.Column("terminal_serial_number", sa.String(100), nullable=True),
        sa.Column("verification_type", sa.String(50), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column(
            "sync_batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("biometric_sync_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        # The idempotency guarantee. Ingestion relies on this index, not on an
        # application-side pre-check, so concurrent replays cannot both win.
        sa.UniqueConstraint(
            "provider",
            "external_transaction_id",
            name="biometric_punches_provider_txn_uq",
        ),
    )
    # Per-employee timeline (the only read shape later phases need).
    op.create_index(
        "biometric_punches_employee_time_idx",
        "biometric_punches",
        ["employee_id", "punch_time"],
    )
    # Same timeline for punches that never mapped - drives which mapping to add.
    op.create_index(
        "biometric_punches_ext_code_time_idx",
        "biometric_punches",
        ["external_employee_code", "punch_time"],
    )
    # Date-range sweeps. Not served by the composite above (employee_id leads it
    # and is nullable).
    op.create_index(
        "biometric_punches_punch_time_idx", "biometric_punches", ["punch_time"]
    )
    # "What arrived late?" - some punches are uploaded the following morning.
    op.create_index(
        "biometric_punches_upload_time_idx", "biometric_punches", ["upload_time"]
    )
    # Batch provenance, and keeps ON DELETE SET NULL off a sequential scan.
    op.create_index(
        "biometric_punches_batch_idx", "biometric_punches", ["sync_batch_id"]
    )

    # 3. biometric_employee_mappings
    op.create_table(
        "biometric_employee_mappings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("provider", sa.String(30), nullable=False),
        sa.Column("external_employee_code", sa.String(64), nullable=False),
        sa.Column(
            "employee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # At most ONE ACTIVE mapping per (provider, external code): an external code
    # can never point at two employees at once. Partial, so superseded rows stay.
    op.create_index(
        "biometric_employee_mappings_active_uq",
        "biometric_employee_mappings",
        ["provider", "external_employee_code"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )
    op.create_index(
        "biometric_employee_mappings_employee_idx",
        "biometric_employee_mappings",
        ["employee_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "biometric_employee_mappings_employee_idx",
        table_name="biometric_employee_mappings",
    )
    op.drop_index(
        "biometric_employee_mappings_active_uq",
        table_name="biometric_employee_mappings",
    )
    op.drop_table("biometric_employee_mappings")

    op.drop_index("biometric_punches_batch_idx", table_name="biometric_punches")
    op.drop_index("biometric_punches_upload_time_idx", table_name="biometric_punches")
    op.drop_index("biometric_punches_punch_time_idx", table_name="biometric_punches")
    op.drop_index("biometric_punches_ext_code_time_idx", table_name="biometric_punches")
    op.drop_index("biometric_punches_employee_time_idx", table_name="biometric_punches")
    # biometric_punches references biometric_sync_batches, so it goes first.
    op.drop_table("biometric_punches")

    op.drop_index(
        "biometric_sync_batches_started_idx", table_name="biometric_sync_batches"
    )
    op.drop_table("biometric_sync_batches")
