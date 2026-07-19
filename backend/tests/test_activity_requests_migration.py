"""Migration 0057 — reconcile activity_requests drift.

Proves the reconcile is safe against BOTH schema shapes:

A. A simulated *production* table (legacy ``requested_*`` columns, per-employee
   partial unique index, no count columns, no ``task_id``) — the reconcile
   renames columns in place, adds the count columns, drops the stale index and
   leaves data + foreign keys intact.
B. The *canonical* schema the current migration chain already produces — the
   reconcile is a no-op and never errors (idempotency).

Everything runs inside ONE dedicated connection/transaction that is rolled back
at the end, so the real (canonical) ``activity_requests`` the rest of the suite
depends on is never disturbed. DDL is transactional in Postgres, so the
``DROP TABLE`` + ``CREATE TABLE`` (and the seeded parent rows) are fully undone
by the rollback. The suite's ``db`` session fixture is deliberately NOT used, so
no second connection ever contends for a lock on ``activity_requests`` while
this test holds it exclusively.
"""
import importlib.util
import pathlib
import uuid

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.orm import Session as SASession

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.database import engine
from app.modules.activity_master.models import LEVEL_ACTIVITY, LEVEL_SUB_ACTIVITY
from app.modules.activity_requests.models import (
    ActivityRequest,
    ActivityRequestStatus,
)

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIG_PATH = _VERSIONS / "0057_reconcile_activity_requests.py"
# 0059 adds pages_count/records_count to this same table. Production applies it
# right after 0057, and the ORM (which these tests read through) expects the
# resulting six-unit shape — so the legacy-shape simulation below must run both
# to reproduce reality. See _apply_0059_columns.
_MIG_0059_PATH = _VERSIONS / "0059_activity_req_pages_records.py"

# Exactly the shape production is running: original 0050 (pre-rewrite) + 0051's
# report_id. Legacy requested_* columns, current_activity_id, the per-employee
# "one pending" partial unique index, and NO count / task_id columns.
_LEGACY_DDL = """
CREATE TABLE activity_requests (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    employee_id uuid NOT NULL,
    current_activity_id uuid,
    requested_project_id uuid NOT NULL,
    requested_activity_id uuid NOT NULL,
    requested_sub_activity_id uuid NOT NULL,
    status varchar(20) NOT NULL DEFAULT 'pending',
    requested_at timestamptz NOT NULL DEFAULT now(),
    approved_by uuid,
    approved_at timestamptz,
    report_id uuid,
    CONSTRAINT activity_requests_pkey PRIMARY KEY (id),
    CONSTRAINT activity_requests_status_valid
        CHECK (status IN ('pending','approved','rejected','cancelled')),
    CONSTRAINT activity_requests_employee_fk FOREIGN KEY (employee_id)
        REFERENCES employees(id) ON DELETE RESTRICT,
    CONSTRAINT activity_requests_current_activity_fk FOREIGN KEY (current_activity_id)
        REFERENCES work_report_tasks(id) ON DELETE SET NULL,
    CONSTRAINT activity_requests_project_fk FOREIGN KEY (requested_project_id)
        REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT activity_requests_activity_fk FOREIGN KEY (requested_activity_id)
        REFERENCES activity_master(id) ON DELETE RESTRICT,
    CONSTRAINT activity_requests_sub_activity_fk FOREIGN KEY (requested_sub_activity_id)
        REFERENCES activity_master(id) ON DELETE RESTRICT,
    CONSTRAINT activity_requests_approved_by_fk FOREIGN KEY (approved_by)
        REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT activity_requests_report_fk FOREIGN KEY (report_id)
        REFERENCES daily_work_reports(id) ON DELETE CASCADE
);
CREATE INDEX activity_requests_employee_idx ON activity_requests (employee_id);
CREATE INDEX activity_requests_status_idx ON activity_requests (status);
CREATE UNIQUE INDEX activity_requests_one_pending_uq
    ON activity_requests (employee_id) WHERE status = 'pending';
CREATE INDEX activity_requests_report_idx ON activity_requests (report_id);
"""


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig0057", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _apply_0059_columns(operations, conn) -> None:
    """Apply 0059's guarded add-column step on this connection.

    The legacy DDL below recreates activity_requests as PRODUCTION ran it (four
    count columns, no pages/records). 0057 alone therefore leaves a table the
    CURRENT ORM cannot read, since the model now maps six units — not a bug in
    either migration, just an incomplete simulation: production runs 0057 then
    0059. Replaying 0059's real body (rather than hand-writing the DDL) keeps
    this test honest if that migration ever changes."""
    spec = importlib.util.spec_from_file_location("mig0059", _MIG_0059_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    cols = {c["name"] for c in sa.inspect(conn).get_columns(mod.TABLE)}
    for name in mod._NEW_COLUMNS:
        if name not in cols:
            operations.add_column(
                mod.TABLE,
                sa.Column(name, sa.Integer(), server_default="0", nullable=False),
            )


def _apply_0060_period_id(operations, conn) -> None:
    """Apply 0060's activity_requests step on this connection.

    Same rationale as _apply_0059_columns: production runs 0057 -> 0059 -> 0060
    (which adds the nullable ``period_id`` -> work_report_periods link), and the
    current ORM maps it — so the legacy-shape simulation must complete the
    chain before reading through the ORM. Guarded so it is a no-op on a table
    that already has the column."""
    cols = {c["name"] for c in sa.inspect(conn).get_columns("activity_requests")}
    if "period_id" not in cols:
        operations.add_column(
            "activity_requests",
            sa.Column(
                "period_id",
                sa.dialects.postgresql.UUID(as_uuid=True),
                sa.ForeignKey(
                    "work_report_periods.id",
                    name="activity_requests_period_id_fkey",
                    ondelete="SET NULL",
                ),
                nullable=True,
            ),
        )


def _cols(conn) -> dict:
    return {c["name"]: c for c in sa.inspect(conn).get_columns("activity_requests")}


def _index_names(conn) -> set[str]:
    return {i["name"] for i in sa.inspect(conn).get_indexes("activity_requests")}


def _seed_parents(conn) -> dict:
    """Insert the minimal parent rows the legacy FKs need, on the SAME
    connection/transaction so there is no cross-connection lock contention."""
    ids = {k: uuid.uuid4() for k in ("emp", "proj", "act", "sub")}
    conn.execute(
        text(
            "INSERT INTO employees (id, employee_code, first_name, last_name) "
            "VALUES (:id, 'LEG-1', 'Leg', 'Acy')"
        ),
        {"id": ids["emp"]},
    )
    conn.execute(
        text("INSERT INTO projects (id, code, name) VALUES (:id, 'LEG-P', 'Legacy')"),
        {"id": ids["proj"]},
    )
    conn.execute(
        text("INSERT INTO activity_master (id, name, level) VALUES (:id, 'Act', :lvl)"),
        {"id": ids["act"], "lvl": LEVEL_ACTIVITY},
    )
    conn.execute(
        text(
            "INSERT INTO activity_master (id, name, level, parent_id) "
            "VALUES (:id, 'Sub', :lvl, :parent)"
        ),
        {"id": ids["sub"], "lvl": LEVEL_SUB_ACTIVITY, "parent": ids["act"]},
    )
    return ids


def test_reconcile_from_production_shape():
    """Requirement A — legacy production table is renamed/augmented in place with
    no data loss, FKs preserved, counts defaulted to zero, stale index dropped,
    current_activity_id kept, task_id NOT added, and the migrated row readable
    through the current ORM."""
    mod = _load_migration()
    legacy_id = uuid.uuid4()

    conn = engine.connect()
    trans = conn.begin()
    try:
        ids = _seed_parents(conn)

        # Replace the canonical table with the legacy production shape + one row.
        conn.exec_driver_sql("DROP TABLE activity_requests CASCADE")
        for stmt in filter(None, (s.strip() for s in _LEGACY_DDL.split(";"))):
            conn.exec_driver_sql(stmt)
        conn.execute(
            text(
                "INSERT INTO activity_requests "
                "(id, employee_id, requested_project_id, requested_activity_id, "
                " requested_sub_activity_id, status) "
                "VALUES (:id, :emp, :proj, :act, :sub, 'pending')"
            ),
            {
                "id": legacy_id,
                "emp": ids["emp"],
                "proj": ids["proj"],
                "act": ids["act"],
                "sub": ids["sub"],
            },
        )

        before = _cols(conn)
        assert "requested_project_id" in before  # sanity: legacy shape in place
        assert "project_id" not in before
        assert "activity_requests_one_pending_uq" in _index_names(conn)

        ops = Operations(MigrationContext.configure(conn))
        mod._reconcile(ops, conn)

        after = _cols(conn)
        # Columns renamed to canonical names, legacy names gone.
        assert "project_id" in after and "requested_project_id" not in after
        assert "activity_id" in after and "requested_activity_id" not in after
        assert "sub_activity_id" in after and "requested_sub_activity_id" not in after
        # Count columns added.
        assert {"tags_count", "docs_count", "bom_count", "spares_count"} <= set(after)
        # current_activity_id kept for compatibility; task_id NOT added.
        assert "current_activity_id" in after
        assert "task_id" not in after
        # activity_id relaxed to nullable (legacy requested_activity_id was NOT NULL).
        assert after["activity_id"]["nullable"] is True
        # Stale per-employee partial unique index dropped, replaced by the
        # per-employee/report guard.
        assert "activity_requests_one_pending_uq" not in _index_names(conn)
        assert "activity_requests_one_pending_per_report_uq" in _index_names(conn)

        # Foreign keys preserved on the renamed columns.
        fk_cols = {
            tuple(f["constrained_columns"])
            for f in sa.inspect(conn).get_foreign_keys("activity_requests")
        }
        assert ("project_id",) in fk_cols
        assert ("activity_id",) in fk_cols
        assert ("sub_activity_id",) in fk_cols
        assert ("employee_id",) in fk_cols

        # Existing data survived the rename and is readable through the ORM,
        # counts defaulting to zero. The ORM maps six units + period_id, so
        # complete the chain (0057 -> 0059 -> 0060) exactly as production does
        # before reading.
        _apply_0059_columns(ops, conn)
        _apply_0060_period_id(ops, conn)
        sess = SASession(bind=conn)
        r = sess.get(ActivityRequest, legacy_id)
        assert r is not None
        assert r.project_id == ids["proj"]
        assert r.activity_id == ids["act"]
        assert r.sub_activity_id == ids["sub"]
        assert r.status == ActivityRequestStatus.pending.value
        assert (r.tags_count, r.docs_count, r.bom_count, r.spares_count) == (0, 0, 0, 0)
        # 0059's units backfill to 0 on a legacy row: no workload was requested.
        assert (r.pages_count, r.records_count) == (0, 0)
        sess.close()

        # Idempotent: a second pass over the now-canonical table is a no-op.
        # Compared against the shape as it stands NOW (0057 + 0059), not the
        # pre-0059 snapshot taken above.
        settled = set(_cols(conn))
        mod._reconcile(ops, conn)
        assert set(_cols(conn)) == settled
    finally:
        trans.rollback()  # undoes the drop/recreate + seeds — canonical restored
        conn.close()


def test_reconcile_is_noop_on_canonical_schema():
    """Requirement B — against the already-canonical schema the current chain
    builds (the live table the suite runs on), the reconcile makes no changes
    and raises nothing."""
    mod = _load_migration()
    conn = engine.connect()
    trans = conn.begin()
    try:
        before = set(_cols(conn))
        assert "project_id" in before  # canonical schema, as built by the chain
        ops = Operations(MigrationContext.configure(conn))
        mod._reconcile(ops, conn)
        assert set(_cols(conn)) == before
    finally:
        trans.rollback()
        conn.close()
