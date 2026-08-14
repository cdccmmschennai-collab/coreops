"""0067 attendance record note

Adds attendance_records.note — the reason a human gave for setting a day the way
they did.

WHY A COLUMN AND NOT THE AUDIT LOG
==================================
The note was already being written to `audit_logs.details` when a PM saved an
attendance decision, and it stays there. But an audit entry answers "what
happened, and when" — it is an append-only event stream. The Records review
screen and the employee's own calendar need to answer a different question:
"what does this day say, right now?" Reconstructing that from the newest matching
audit row would make an event log double as a current-state store, which gets
ambiguous the moment a day is edited twice.

So the reason lives with the day it explains, and the audit trail keeps the
history of how it got there. The two are not redundant: one is state, one is
evidence of change.

Purely additive and backward-compatible:

- Nullable TEXT with no server default, so every one of the existing
  attendance_records rows is untouched and reads NULL. Nothing is backfilled and
  nothing is guessed — a day nobody explained simply has no explanation.
- No existing column, constraint, index or enum is modified.
- Every current INSERT path keeps working unchanged: the bulk attendance sheet,
  the attendance form and the seed scripts all omit the field.
- TEXT rather than VARCHAR(n): the length bound that matters is the API's
  (`MAX_NOTE_LEN = 500` in attendance/schemas.py), and keeping it in one place
  means raising it later is not a migration.

Downgrade drops the column, and the only thing lost is the stored reasons — the
same text remains readable in `audit_logs.details` for every decision recorded
after this feature shipped.

Revision ID: 0067_attendance_record_note
Revises: 0066_biometric_punch_ingestion
Create Date: 2026-08-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0067_attendance_record_note"
down_revision: Union[str, None] = "0066_biometric_punch_ingestion"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_records",
        sa.Column("note", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("attendance_records", "note")
