"""0059 activity_requests PAGES/RECORDS workload hints

Migration 0058 gave work_report_tasks the pages_count/records_count columns but
left activity_requests on the original four units, making it the last place in
the system that could not express a PAGES or RECORDS workload. An employee could
not raise "please add MTL-DOC.O&M MANNUALS DATA POPULATION, 500 PAGES" without
the quantity being silently dropped.

Pure additive schema — two columns, same shape as the four already there
(INTEGER NOT NULL DEFAULT 0). No data movement: unlike 0058 there is no historical
unit to convert, because activity_requests never stored a unit. Existing rows
backfill to 0, which is exactly "no page/record workload requested".

These counts are REQUEST WORKLOAD HINTS ONLY. They are copied onto the created
work_report_tasks row when a PM approves, and from that point the normal
benchmark rules apply to the report row — the request itself never creates
benchmark performance, never completes a task, and never touches
WorkItem.completed_on.

Named `0059_activity_req_pages_records`, not `..._activity_request_...`:
alembic_version.version_num is VARCHAR(32) and the fuller name is 35 characters,
so it fails at the final version stamp AFTER the DDL has run. (0057, at exactly
32, is already on the ceiling.) The abbreviation is the whole reason for the
shorter middle word — keep any future revision id at 32 characters or fewer.

Revision ID: 0059_activity_req_pages_records
Revises: 0058_pages_records_units
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0059_activity_req_pages_records"
down_revision: Union[str, None] = "0058_pages_records_units"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "activity_requests"
_NEW_COLUMNS = ("pages_count", "records_count")


def _column_names(bind) -> set:
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _column_names(bind)
    # Inspection-guarded, matching 0057's convention for this same table: this
    # table has a history of production drift, so never assume its exact shape.
    for name in _NEW_COLUMNS:
        if name not in cols:
            op.add_column(
                TABLE,
                sa.Column(name, sa.Integer(), server_default="0", nullable=False),
            )


def downgrade() -> None:
    """Refuses rather than destroy a requested workload.

    Dropping these columns while a pending request carries a page/record count
    would silently discard what the employee asked for, and there is no other
    column to fold the value into (a page is not a document). So the downgrade
    refuses whenever any non-zero value exists; when everything is zero the drop
    is lossless and proceeds. Same principle as 0058's downgrade.
    """
    bind = op.get_bind()
    cols = _column_names(bind)
    present = [c for c in _NEW_COLUMNS if c in cols]
    if not present:
        return

    predicate = " OR ".join(f"{c} <> 0" for c in present)
    in_use = bind.execute(
        text(f"SELECT count(*) AS n FROM {TABLE} WHERE {predicate}")
    ).one().n
    if in_use:
        raise RuntimeError(
            f"0059 downgrade refused: {in_use} activity_requests row(s) carry a "
            f"non-zero pages_count/records_count. Dropping those columns would "
            f"discard the workload an employee actually requested, and there is "
            f"no equivalent legacy unit to fold it into. Resolve or reject those "
            f"requests first."
        )

    for name in reversed(present):
        op.drop_column(TABLE, name)
