"""0088 attendance comp off link

Comp Off Phase 4 - an APPROVED comp off request now marks its `off_date` in
attendance, and this column is how that row says which request it came from.

    attendance_records.comp_off_request_id   UUID NULL -> comp_off_requests.id

WHY A COLUMN AND NOT THE NOTE OR THE AUDIT TRAIL
================================================
The link has to be queryable from the attendance row and has to survive a PM
editing that row's note. A note is free text anybody with the dialog rewrites;
an audit entry is durable but cannot be constrained. A foreign key is both, and
it lets the database itself enforce the rule that matters:

    UNIQUE (comp_off_request_id)   one approved request marks at most ONE day

so an approval applied twice - a retry, a race the request lock somehow missed -
fails on the constraint instead of writing a second day off. NULLs do not
collide, so every existing row (all of them NULL) is unaffected.

NULLABLE, AND NOTHING IS BACKFILLED
===================================
NULL means "not written by a comp off approval" - every PM-entered row, every
leave row, and the legacy PM-entered `comp_off` rows, which name no request and
therefore cannot be linked to one. Nothing is guessed.

ON DELETE RESTRICT: a request that backs a day of attendance is not deleted out
from under it. Requests are never hard-deleted by the application anyway.

Revision ID: 0088_attendance_comp_off_link
Revises: 0087_comp_off_requests
Create Date: 2026-10-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Max 32 chars: `alembic_version.version_num` is VARCHAR(32).
revision: str = "0088_attendance_comp_off_link"
down_revision: Union[str, None] = "0087_comp_off_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attendance_records",
        sa.Column(
            "comp_off_request_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "comp_off_requests.id",
                name="attendance_comp_off_request_fk",
                ondelete="RESTRICT",
            ),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "attendance_comp_off_request_uq", "attendance_records", ["comp_off_request_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "attendance_comp_off_request_uq", "attendance_records", type_="unique"
    )
    op.drop_constraint(
        "attendance_comp_off_request_fk", "attendance_records", type_="foreignkey"
    )
    op.drop_column("attendance_records", "comp_off_request_id")
