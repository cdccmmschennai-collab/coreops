"""0057 reconcile activity_requests (production drift repair)

Migration 0050 was edited **after** it had already been applied to production.
The version production actually ran created the table with the *legacy* shape:

    current_activity_id, requested_project_id, requested_activity_id,
    requested_sub_activity_id  (+ a per-employee "one pending" partial unique
    index, and no count columns / no task_id)

The file was later rewritten to the *canonical* shape the ORM now expects:

    project_id, activity_id (nullable), sub_activity_id,
    tags_count / docs_count / bom_count / spares_count

Because Alembic still considers 0050 applied, it never reconciles the two, so
production is missing ``project_id`` (hence
``UndefinedColumn: activity_requests.project_id does not exist``) and the count
columns, while a freshly-built local DB already has the canonical columns.

This migration reconciles **both** shapes with pure inspection-guarded DDL:

* legacy ``requested_*`` columns -> canonical names (rename preserves values +
  foreign keys);
* ``activity_id`` forced nullable (legacy ``requested_activity_id`` was NOT
  NULL, the ORM allows null);
* the four ``*_count`` columns added when absent (INTEGER NOT NULL DEFAULT 0);
* the stale per-employee ``activity_requests_one_pending_uq`` partial unique
  index dropped when present (the ORM no longer declares it; one-pending is now
  enforced per *report* in the service).

Deliberately NOT touched:

* ``current_activity_id`` is kept for compatibility (see task note) — it is an
  unmapped column and harmless; removing it needs a separate reviewed step.
* ``task_id`` is neither added nor required — the Tasks module was removed and
  no runtime code reads/writes it, so the stale ORM mapping is dropped instead
  (see app/modules/activity_requests/models.py). On clean DBs the column may
  still exist (created by the rewritten 0050); it is left in place, unmapped.
* the ``status`` CHECK constraint is left as-is so any legacy ``cancelled`` rows
  survive; the service only ever writes pending/approved/rejected.

Safe (and idempotent) whether run against the old production shape or an
already-canonical local schema. No DROP TABLE / TRUNCATE / DELETE.

Revision ID: 0057_reconcile_activity_requests
Revises: 0056_work_items
Create Date: 2026-07-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0057_reconcile_activity_requests"
down_revision: Union[str, None] = "0056_work_items"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "activity_requests"

# legacy production column -> canonical ORM column
_RENAMES = (
    ("requested_project_id", "project_id"),
    ("requested_activity_id", "activity_id"),
    ("requested_sub_activity_id", "sub_activity_id"),
)
_COUNT_COLUMNS = ("tags_count", "docs_count", "bom_count", "spares_count")


def _column_names(bind) -> set[str]:
    return {c["name"] for c in sa.inspect(bind).get_columns(TABLE)}


def _index_names(bind) -> set[str]:
    return {i["name"] for i in sa.inspect(bind).get_indexes(TABLE)}


def _reconcile(operations, bind) -> None:
    """The actual, inspection-guarded reconciliation. Kept as a helper taking an
    explicit ``operations`` object so it can be unit-tested against a simulated
    production table (see tests/test_activity_requests_migration.py) as well as
    driven by Alembic's global ``op`` proxy from :func:`upgrade`."""
    cols = _column_names(bind)

    # 1. Rename legacy requested_* columns only when the legacy name is present
    #    and the canonical target is absent. Renaming preserves data + FKs.
    for legacy, canonical in _RENAMES:
        if legacy in cols and canonical not in cols:
            operations.alter_column(TABLE, legacy, new_column_name=canonical)

    cols = _column_names(bind)

    # 2. activity_id must be nullable (legacy requested_activity_id was NOT NULL;
    #    the ORM permits null). Idempotent — a no-op if already nullable.
    if "activity_id" in cols:
        operations.alter_column(
            TABLE,
            "activity_id",
            existing_type=postgresql.UUID(as_uuid=True),
            nullable=True,
        )

    # 3. Add the four count columns when missing (present on canonical schema).
    for name in _COUNT_COLUMNS:
        if name not in cols:
            operations.add_column(
                TABLE,
                sa.Column(name, sa.Integer(), server_default="0", nullable=False),
            )

    # 4. Drop the stale per-*employee* partial unique index if it survives from
    #    the legacy schema. The service rule is now one pending request per
    #    employee/report, so the old per-employee guard is both wrong (it would
    #    block a second report's request) and no longer declared by the ORM.
    #    Dropping an index never loses data.
    if "activity_requests_one_pending_uq" in _index_names(bind):
        operations.drop_index(
            "activity_requests_one_pending_uq", table_name=TABLE
        )

    # 5. Replace it with database-level protection matching the current rule:
    #    at most one PENDING request per (employee_id, report_id). Scoped to
    #    report_id IS NOT NULL so legacy rows (report_id NULL, pre-0051) are
    #    never constrained. Created only when absent, so the migration is
    #    idempotent on both the legacy and the already-canonical schema.
    if "activity_requests_one_pending_per_report_uq" not in _index_names(bind):
        operations.create_index(
            "activity_requests_one_pending_per_report_uq",
            TABLE,
            ["employee_id", "report_id"],
            unique=True,
            postgresql_where=sa.text(
                "status = 'pending' AND report_id IS NOT NULL"
            ),
        )


def upgrade() -> None:
    _reconcile(op, op.get_bind())


def downgrade() -> None:
    # Intentional structural no-op. This migration reconciles two divergent
    # historical shapes into one; its inverse is ambiguous (which shape do we
    # restore?), and every candidate reverse operation is destructive (dropping
    # the count columns / renaming canonical -> requested_* would break the ORM
    # and lose data on canonical databases). The reconciled schema is a strict,
    # backward-compatible superset, so leaving it in place on downgrade is the
    # only structurally safe choice.
    pass
