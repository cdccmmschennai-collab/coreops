"""Migration 0063 safety - schema shape, reversibility, and non-interference.

Follows the house pattern for migration suites (see test_split_day_migration.py):
assert the real schema in the live test database, then rehearse
downgrade -> upgrade against it.
"""
import importlib.util
import pathlib

import pytest
from sqlalchemy import text

_VERSIONS = pathlib.Path(__file__).resolve().parents[1] / "alembic" / "versions"
_MIG_PATH = _VERSIONS / "0063_biometric_punch_ingestion.py"

PREVIOUS_HEAD = "0062_leave_cancellation_status"
THIS_REVISION = "0063_biometric_punch_ingestion"

NEW_TABLES = (
    "biometric_punches",
    "biometric_sync_batches",
    "biometric_employee_mappings",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig0063", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


def _table_exists(db, name: str) -> bool:
    return db.execute(
        text(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = :n"
        ),
        {"n": name},
    ).scalar_one() == 1


def _columns(db, table: str) -> dict[str, str]:
    rows = db.execute(
        text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = :t"
        ),
        {"t": table},
    ).all()
    return {name: dtype for name, dtype in rows}


def _indexes(db, table: str) -> set[str]:
    return set(
        db.execute(
            text("SELECT indexname FROM pg_indexes WHERE tablename = :t"), {"t": table}
        ).scalars()
    )


# ── revision wiring ─────────────────────────────────────────────────────────

def test_revision_chains_onto_the_previous_head():
    assert MIG.revision == THIS_REVISION
    assert MIG.down_revision == PREVIOUS_HEAD
    assert MIG.branch_labels is None
    assert MIG.depends_on is None


def test_single_alembic_head():
    """Exactly one head: no branch was introduced."""
    revisions, downs = set(), set()
    for path in _VERSIONS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for line in source.splitlines():
            if line.startswith("revision: str = "):
                revisions.add(line.split("=", 1)[1].strip().strip('"'))
            elif line.startswith("down_revision: Union[str, None] = "):
                value = line.split("=", 1)[1].strip().strip('"')
                if value != "None":
                    downs.add(value)
    heads = revisions - downs
    assert heads == {THIS_REVISION}, heads


def test_database_is_stamped_at_this_revision(db):
    current = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert current == THIS_REVISION


# ── schema shape ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("table", NEW_TABLES)
def test_new_tables_exist(db, table):
    assert _table_exists(db, table)


def test_punch_columns_and_types(db):
    cols = _columns(db, "biometric_punches")
    expected = {
        "id": "uuid",
        "provider": "character varying",
        "external_transaction_id": "character varying",
        "external_employee_code": "character varying",
        "employee_id": "uuid",
        "punch_time": "timestamp with time zone",
        "upload_time": "timestamp with time zone",
        "received_at": "timestamp with time zone",
        "raw_punch_state": "character varying",
        "punch_state_display": "character varying",
        "terminal_alias": "character varying",
        "terminal_serial_number": "character varying",
        "verification_type": "character varying",
        "source": "character varying",
        "sync_batch_id": "uuid",
        "raw_payload": "jsonb",
        "created_at": "timestamp with time zone",
    }
    assert cols == expected


def test_punches_are_immutable_by_shape(db):
    """No updated_at and no deleted_at: a punch is a fact, not a record to edit."""
    cols = _columns(db, "biometric_punches")
    assert "updated_at" not in cols
    assert "deleted_at" not in cols


def test_employee_id_is_nullable_so_unmapped_punches_survive(db):
    nullable = db.execute(
        text(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_name = 'biometric_punches' AND column_name = 'employee_id'"
        )
    ).scalar_one()
    assert nullable == "YES"


def test_punch_unique_constraint_is_the_idempotency_anchor(db):
    cols = db.execute(
        text(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.constraint_name = 'biometric_punches_provider_txn_uq' "
            "ORDER BY kcu.ordinal_position"
        )
    ).scalars().all()
    assert cols == ["provider", "external_transaction_id"]


def test_punch_indexes_present(db):
    assert {
        "biometric_punches_employee_time_idx",
        "biometric_punches_ext_code_time_idx",
        "biometric_punches_punch_time_idx",
        "biometric_punches_upload_time_idx",
        "biometric_punches_batch_idx",
    } <= _indexes(db, "biometric_punches")


def test_employee_fk_is_set_null_not_cascade(db):
    """Purging an employee must never delete attendance evidence."""
    rule = db.execute(
        text(
            "SELECT rc.delete_rule FROM information_schema.referential_constraints rc "
            "JOIN information_schema.table_constraints tc "
            "  ON rc.constraint_name = tc.constraint_name "
            "WHERE tc.table_name = 'biometric_punches' "
            "  AND tc.constraint_type = 'FOREIGN KEY' "
            "  AND rc.unique_constraint_name IN ("
            "     SELECT constraint_name FROM information_schema.table_constraints "
            "     WHERE table_name = 'employees' AND constraint_type = 'PRIMARY KEY')"
        )
    ).scalar_one()
    assert rule == "SET NULL"


def test_sync_batch_status_check_constraint(db):
    clause = db.execute(
        text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'biometric_sync_batches_status_valid'"
        )
    ).scalar_one()
    for status in ("processing", "completed", "completed_with_errors", "failed"):
        assert status in clause


def test_sync_batch_key_unique_constraint(db):
    cols = db.execute(
        text(
            "SELECT kcu.column_name FROM information_schema.key_column_usage kcu "
            "WHERE kcu.constraint_name = 'biometric_sync_batches_key_uq' "
            "ORDER BY kcu.ordinal_position"
        )
    ).scalars().all()
    assert cols == ["provider", "connector_id", "batch_key"]


def test_mapping_active_unique_index_is_partial(db):
    definition = db.execute(
        text(
            "SELECT indexdef FROM pg_indexes "
            "WHERE indexname = 'biometric_employee_mappings_active_uq'"
        )
    ).scalar_one()
    assert "UNIQUE" in definition
    assert "WHERE" in definition and "is_active" in definition


def test_status_check_rejects_an_unknown_status(db):
    """The CHECK constraint is real, not decorative."""
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO biometric_sync_batches "
                "(provider, connector_id, batch_key, status) "
                "VALUES ('easytime', 'c1', 'k1', 'bogus')"
            )
        )
    db.rollback()


# ── non-interference with the existing schema ───────────────────────────────

def test_existing_attendance_schema_is_untouched(db):
    """0063 is additive: attendance_records keeps exactly the shape it had."""
    cols = _columns(db, "attendance_records")
    assert set(cols) == {
        "id",
        "employee_id",
        "attendance_date",
        "check_in_at",
        "check_out_at",
        "total_minutes",
        "overtime_minutes",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    }


def test_no_biometric_column_leaked_into_existing_tables(db):
    for table in ("attendance_records", "employees", "leave_requests"):
        cols = _columns(db, table)
        assert not [c for c in cols if "punch" in c or "biometric" in c], table


# ── reversibility ───────────────────────────────────────────────────────────

def test_downgrade_and_upgrade_rehearsal(db):
    """Walk the schema down to 0062 and back to head against the live test
    database. Defined LAST in this file so it runs last (pytest keeps definition
    order); `_clean_state` truncates per test, so no data depends on the tables
    being recreated."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    db.close()  # release the connection so the DDL does not deadlock

    command.downgrade(cfg, PREVIOUS_HEAD)
    with db.bind.connect() as conn:
        for table in NEW_TABLES:
            present = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = :n"
                ),
                {"n": table},
            ).scalar_one()
            assert present == 0, f"{table} survived downgrade"
        # The downgrade touched nothing else.
        assert conn.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_name = 'attendance_records'"
            )
        ).scalar_one() == 1

    command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        for table in NEW_TABLES:
            present = conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_name = :n"
                ),
                {"n": table},
            ).scalar_one()
            assert present == 1, f"{table} missing after re-upgrade"
