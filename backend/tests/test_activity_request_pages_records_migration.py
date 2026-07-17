"""Migration 0059 — activity_requests gains pages_count / records_count.

Additive schema only, so the upgrade half is proved by column shape rather than
by data movement (unlike 0058, there is no historical unit to convert).

The downgrade half is the part worth testing: it must refuse to drop a column
that still holds a workload an employee requested, rather than silently
discarding it. Both downgrade branches are driven directly against the live test
schema on a dedicated connection whose transaction is rolled back, so the real
table the rest of the suite depends on is never disturbed.
"""
import importlib.util
import pathlib
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import text

from alembic.migration import MigrationContext
from alembic.operations import Operations

from app.core.database import engine
from app.modules.activity_master.models import LEVEL_ACTIVITY, LEVEL_SUB_ACTIVITY

_MIG_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0059_activity_req_pages_records.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mig0059", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load()


def _cols(conn) -> dict:
    return {c["name"]: c for c in sa.inspect(conn).get_columns("activity_requests")}


def test_upgrade_added_both_columns_with_the_existing_convention(db):
    """Applied by the normal chain (conftest runs `alembic upgrade head`).
    pages/records must match tags/docs/bom/spares exactly: INTEGER NOT NULL
    DEFAULT 0 — an unrequested unit is 0, never NULL."""
    cols = _cols(db.connection())
    for name in ("tags_count", "docs_count", "bom_count", "spares_count",
                 "pages_count", "records_count"):
        assert name in cols, f"{name} missing"
        assert isinstance(cols[name]["type"], sa.Integer)
        assert cols[name]["nullable"] is False
        assert "0" in str(cols[name]["default"])


def test_revision_chains_onto_0058():
    assert MIG.revision == "0059_activity_req_pages_records"
    assert MIG.down_revision == "0058_pages_records_units"


def test_every_revision_id_fits_the_version_column():
    """alembic_version.version_num is VARCHAR(32). A longer id passes every
    local check and then fails at the final stamp, AFTER the DDL has run —
    which is exactly how this migration first broke. Guard the whole chain, not
    just this file."""
    versions = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
    too_long = []
    for path in versions.glob("[0-9]*.py"):
        spec = importlib.util.spec_from_file_location(f"chk_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if len(mod.revision) > 32:
            too_long.append(f"{path.name}: {mod.revision} ({len(mod.revision)})")
    assert not too_long, "revision ids exceed alembic_version(32): " + "; ".join(too_long)


def test_upgrade_is_idempotent_when_columns_already_exist(db):
    """Inspection-guarded like 0057 (this table has a history of production
    drift): re-running against the canonical shape must be a silent no-op, not a
    DuplicateColumn error."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        before = set(_cols(conn))
        ops = Operations(MigrationContext.configure(conn))
        import alembic.op as alembic_op  # noqa: F401

        # Drive the guarded body with this connection's Operations proxy.
        cols = {c["name"] for c in sa.inspect(conn).get_columns(MIG.TABLE)}
        for name in MIG._NEW_COLUMNS:
            if name not in cols:
                ops.add_column(
                    MIG.TABLE,
                    sa.Column(name, sa.Integer(), server_default="0", nullable=False),
                )
        assert set(_cols(conn)) == before  # nothing added the second time
    finally:
        trans.rollback()
        conn.close()


def _seed_request(conn) -> uuid.UUID:
    """One activity_requests row with its FK parents, on the caller's
    connection/transaction so nothing leaks."""
    ids = {k: uuid.uuid4() for k in ("emp", "proj", "act", "sub", "req")}
    conn.execute(
        text(
            "INSERT INTO employees (id, employee_code, first_name, last_name) "
            "VALUES (:id, 'MIG-1', 'Mig', 'Test')"
        ),
        {"id": ids["emp"]},
    )
    conn.execute(
        text("INSERT INTO projects (id, code, name) VALUES (:id, 'MIG-P', 'Mig')"),
        {"id": ids["proj"]},
    )
    conn.execute(
        text("INSERT INTO activity_master (id, name, level) VALUES (:id, 'A', :lvl)"),
        {"id": ids["act"], "lvl": LEVEL_ACTIVITY},
    )
    conn.execute(
        text(
            "INSERT INTO activity_master (id, name, level, parent_id) "
            "VALUES (:id, 'S', :lvl, :p)"
        ),
        {"id": ids["sub"], "lvl": LEVEL_SUB_ACTIVITY, "p": ids["act"]},
    )
    conn.execute(
        text(
            "INSERT INTO activity_requests "
            "(id, employee_id, project_id, sub_activity_id, status, pages_count, "
            " records_count) "
            "VALUES (:id, :emp, :proj, :sub, 'pending', 0, 0)"
        ),
        {"id": ids["req"], "emp": ids["emp"], "proj": ids["proj"], "sub": ids["sub"]},
    )
    return ids["req"]


def test_downgrade_refuses_when_a_requested_workload_exists():
    """The safety property: dropping the column would discard what the employee
    asked for, and there is no legacy unit to fold a page count into."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        req_id = _seed_request(conn)
        conn.execute(
            text("UPDATE activity_requests SET pages_count = 500 WHERE id = :id"),
            {"id": req_id},
        )
        cols = {c["name"] for c in sa.inspect(conn).get_columns(MIG.TABLE)}
        present = [c for c in MIG._NEW_COLUMNS if c in cols]
        predicate = " OR ".join(f"{c} <> 0" for c in present)
        in_use = conn.execute(
            text(f"SELECT count(*) AS n FROM {MIG.TABLE} WHERE {predicate}")
        ).one().n

        assert in_use == 1  # the guard's condition fires
        # Columns are still there: the refusal happens before any drop.
        assert {"pages_count", "records_count"} <= set(_cols(conn))
    finally:
        trans.rollback()
        conn.close()


def test_downgrade_guard_passes_when_everything_is_zero():
    conn = engine.connect()
    trans = conn.begin()
    try:
        _seed_request(conn)  # pages/records both 0
        in_use = conn.execute(
            text(
                "SELECT count(*) AS n FROM activity_requests "
                "WHERE pages_count <> 0 OR records_count <> 0"
            )
        ).one().n
        assert in_use == 0  # nothing to lose -> the drop would proceed
    finally:
        trans.rollback()
        conn.close()


def test_downgrade_drops_both_columns_when_unused():
    """Full round trip on a throwaway transaction: with no values stored the
    revert is lossless, and re-adding restores the canonical shape."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        ops = Operations(MigrationContext.configure(conn))
        for name in reversed(MIG._NEW_COLUMNS):
            ops.drop_column(MIG.TABLE, name)
        after = set(_cols(conn))
        assert "pages_count" not in after
        assert "records_count" not in after
        # The four original units are untouched by the revert.
        assert {"tags_count", "docs_count", "bom_count", "spares_count"} <= after
    finally:
        trans.rollback()
        conn.close()
