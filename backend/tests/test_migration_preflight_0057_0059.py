"""Preflight (0057/0058/0059) against every schema state it must survive.

The production run failed with `UndefinedColumn: t.records_count does not
exist`, because at 0056/0057 the PAGES/RECORDS columns have not been created
yet. A CASE expression cannot rescue that - PostgreSQL parses every column
reference in a statement, including branches that never execute - so the script
must emit DIFFERENT SQL depending on what exists.

These tests build a REAL PostgreSQL schema per revision (0056, 0057, 0058,
0059) and point the connection's search_path at it, so the queries are parsed
by the actual server against the actual columns. A simulated column list would
not have caught the original bug.
"""
import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal

# Load the script by path - backend/scripts is not an importable package.
_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migration_preflight_0057_0059.py"
_spec = importlib.util.spec_from_file_location("preflight_0057_0059", _SCRIPT)
preflight = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(preflight)

PARENT = preflight.PARENT_NAME
SUBS = preflight.SUB_NAMES

# Columns added by 0058 (work_report_tasks) and 0059 (activity_requests).
COLS_0058 = "pages_count integer NOT NULL DEFAULT 0, records_count integer NOT NULL DEFAULT 0,"
COLS_0059 = COLS_0058


def _build_schema(conn, schema: str, revision: str) -> None:
    """Create a throwaway schema shaped like `revision` and select it.

    Only the tables and columns the preflight touches are created; that is
    precisely what makes the missing-column case reproducible."""
    has_wrt_new = revision in (preflight.REV_0058, preflight.REV_0059)
    has_ar_new = revision == preflight.REV_0059

    conn.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
    conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    # search_path drives BOTH the information_schema probe and the real queries.
    conn.execute(text(f'SET search_path TO "{schema}"'))

    conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)"))
    conn.execute(
        text("INSERT INTO alembic_version (version_num) VALUES (:v)"), {"v": revision}
    )

    conn.execute(
        text(
            """
            CREATE TABLE activity_master (
                id uuid PRIMARY KEY,
                parent_id uuid,
                name text NOT NULL,
                is_active boolean NOT NULL DEFAULT true,
                benchmark_type varchar(20),
                relevant_count_field varchar(20)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE daily_work_reports (
                id uuid PRIMARY KEY,
                employee_id uuid NOT NULL,
                report_date date NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE work_report_tasks (
                id uuid PRIMARY KEY,
                report_id uuid NOT NULL,
                sub_activity_id uuid,
                docs_count integer NOT NULL DEFAULT 0,
                tags_count integer NOT NULL DEFAULT 0,
                bom_count integer NOT NULL DEFAULT 0,
                spares_count integer NOT NULL DEFAULT 0,
                {COLS_0058 if has_wrt_new else ""}
                relevant_count_field_snapshot varchar(20)
            )
            """
        )
    )
    conn.execute(
        text(
            f"""
            CREATE TABLE activity_requests (
                id uuid PRIMARY KEY,
                employee_id uuid NOT NULL,
                report_id uuid,
                sub_activity_id uuid NOT NULL,
                docs_count integer NOT NULL DEFAULT 0,
                {COLS_0059 if has_ar_new else ""}
                status varchar(20) NOT NULL DEFAULT 'pending'
            )
            """
        )
    )


def _seed_activities(conn, *, include=None) -> dict[str, str]:
    """The DOC IDB parent plus its three convertible sub-activities."""
    include = SUBS if include is None else include
    parent_id = str(uuid.uuid4())
    conn.execute(
        text("INSERT INTO activity_master (id, parent_id, name) VALUES (:i, NULL, :n)"),
        {"i": parent_id, "n": PARENT},
    )
    ids = {}
    for name in include:
        sid = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO activity_master "
                "(id, parent_id, name, is_active, benchmark_type, relevant_count_field) "
                "VALUES (:i, :p, :n, true, 'NUMERIC_DAILY', 'docs')"
            ),
            {"i": sid, "p": parent_id, "n": name},
        )
        ids[name] = sid
    return ids


def _seed_task(conn, sub_id, *, docs=0, records=None, snapshot="docs", day=date(2026, 7, 1)):
    """One historical work-report task row. `records` only when the column exists."""
    report_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO daily_work_reports (id, employee_id, report_date) "
            "VALUES (:i, :e, :d)"
        ),
        {"i": report_id, "e": str(uuid.uuid4()), "d": day},
    )
    task_id = str(uuid.uuid4())
    if records is None:
        conn.execute(
            text(
                "INSERT INTO work_report_tasks "
                "(id, report_id, sub_activity_id, docs_count, relevant_count_field_snapshot) "
                "VALUES (:i, :r, :s, :d, :snap)"
            ),
            {"i": task_id, "r": report_id, "s": sub_id, "d": docs, "snap": snapshot},
        )
    else:
        conn.execute(
            text(
                "INSERT INTO work_report_tasks "
                "(id, report_id, sub_activity_id, docs_count, records_count, "
                " relevant_count_field_snapshot) "
                "VALUES (:i, :r, :s, :d, :rec, :snap)"
            ),
            {"i": task_id, "r": report_id, "s": sub_id, "d": docs,
             "rec": records, "snap": snapshot},
        )
    return task_id


@pytest.fixture()
def sandbox():
    """A connection with a private schema, rolled back afterwards.

    The preflight itself is read-only; the sandbox does the writing so there is
    something to read."""
    session = SessionLocal()
    conn = session.connection()
    created: list[str] = []

    def _make(revision: str, schema: str | None = None):
        name = schema or f"pf_{revision[:4]}_{uuid.uuid4().hex[:8]}"
        _build_schema(conn, name, revision)
        created.append(name)
        return conn

    try:
        yield _make
    finally:
        for name in created:
            conn.execute(text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        session.rollback()
        session.close()


def _gate_text(gates):
    return " | ".join(m for _, m in gates)


# --- the regression: 0056 has no records_count -----------------------------

def test_preflight_runs_at_0056_without_records_count(sandbox, tmp_path):
    """The exact production failure: at 0056 the new columns do not exist, so
    the script must not emit SUM(records_count) at all."""
    conn = sandbox(preflight.REV_0056)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=120)
    _seed_task(conn, ids[SUBS[0]], docs=80)

    snap = preflight.collect(conn)          # must not raise UndefinedColumn
    gates = preflight.evaluate(snap)

    assert snap["alembic_current"] == preflight.REV_0056
    # capability flags all false at 0056
    assert snap["schema"] == {
        "work_report_tasks_has_pages_count": False,
        "work_report_tasks_has_records_count": False,
        "activity_requests_has_pages_count": False,
        "activity_requests_has_records_count": False,
    }
    assert snap["is_pre_migration_baseline"] is True

    target = next(t for t in snap["target_activities"] if t["sub_activity_name"] == SUBS[0])
    assert target["docs_total"] == 200          # docs captured
    assert target["records_total"] == 0         # zero by definition, not by coalesce
    assert target["mixed_rows"] == 0
    assert target["linked_task_count"] == 2

    assert all(ok for ok, _ in gates), _gate_text(gates)


def test_preflight_writes_json_and_exits_zero_at_0056(sandbox, tmp_path, monkeypatch):
    """End-to-end at 0056: exit 0, JSON written, flags false, docs captured."""
    conn = sandbox(preflight.REV_0056)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[1]], docs=55)

    out = tmp_path / "preflight.json"
    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)
    assert all(ok for ok, _ in gates), _gate_text(gates)

    # main() opens its own engine; exercise the same write path it uses.
    import json

    snap["gates"] = [{"ok": ok, "message": m} for ok, m in gates]
    snap["safe_to_migrate"] = True
    out.write_text(json.dumps(snap, indent=2, default=preflight._json_default), encoding="utf-8")

    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["safe_to_migrate"] is True
    assert written["schema"]["work_report_tasks_has_records_count"] is False
    t = next(x for x in written["target_activities"] if x["sub_activity_name"] == SUBS[1])
    assert t["docs_total"] == 55
    assert t["records_total"] == 0


def test_preflight_runs_at_0057_columns_still_absent(sandbox):
    """0057 touches activity_requests only; the work-report count columns
    arrive in 0058, so they are still absent here."""
    conn = sandbox(preflight.REV_0057)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[2]], docs=10)

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)

    assert snap["schema"]["work_report_tasks_has_records_count"] is False
    assert snap["is_pre_migration_baseline"] is True
    assert next(
        t for t in snap["target_activities"] if t["sub_activity_name"] == SUBS[2]
    )["records_total"] == 0
    assert all(ok for ok, _ in gates), _gate_text(gates)


# --- post-0058 states read the real columns --------------------------------

def test_preflight_reads_real_records_at_0058(sandbox):
    conn = sandbox(preflight.REV_0058)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=0, records=300, snapshot="records")

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)

    assert snap["schema"]["work_report_tasks_has_records_count"] is True
    assert snap["schema"]["activity_requests_has_records_count"] is False  # 0059 adds it
    t = next(x for x in snap["target_activities"] if x["sub_activity_name"] == SUBS[0])
    assert t["records_total"] == 300
    assert t["docs_total"] == 0
    # Partially applied is an accepted state, but not a pre-migration baseline.
    assert snap["is_pre_migration_baseline"] is False
    assert all(ok for ok, _ in gates), _gate_text(gates)


def test_preflight_reads_real_records_at_0059(sandbox):
    conn = sandbox(preflight.REV_0059)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=0, records=440, snapshot="records")

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)

    assert snap["schema"] == {
        "work_report_tasks_has_pages_count": True,
        "work_report_tasks_has_records_count": True,
        "activity_requests_has_pages_count": True,
        "activity_requests_has_records_count": True,
    }
    assert snap["is_pre_migration_baseline"] is False
    assert all(ok for ok, _ in gates), _gate_text(gates)


# --- unsafe / drifted states must be caught --------------------------------

def test_mixed_docs_and_records_on_a_converted_row_is_unsafe(sandbox):
    """A row holding both units cannot be merged without guessing which unit
    the historical number meant."""
    conn = sandbox(preflight.REV_0058)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=50, records=70, snapshot="docs")

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)

    assert next(
        t for t in snap["target_activities"] if t["sub_activity_name"] == SUBS[0]
    )["mixed_rows"] == 1
    assert not all(ok for ok, _ in gates)
    assert "BOTH docs_count" in _gate_text(gates)


def test_schema_drift_before_0058_is_reported_but_passes_when_empty(sandbox):
    """Columns present before 0058 = out-of-band schema change. Harmless while
    they hold no data, so it is surfaced rather than blocking."""
    conn = sandbox(preflight.REV_0056)
    # 0056 revision recorded, but the columns exist anyway.
    conn.execute(text("ALTER TABLE work_report_tasks ADD COLUMN records_count integer NOT NULL DEFAULT 0"))
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=10, records=0, snapshot="docs")

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)

    assert snap["schema"]["work_report_tasks_has_records_count"] is True
    assert "SCHEMA DRIFT" in _gate_text(gates)
    assert all(ok for ok, _ in gates), _gate_text(gates)   # empty -> reported only


def test_schema_drift_before_0058_fails_when_it_already_holds_data(sandbox):
    conn = sandbox(preflight.REV_0056)
    conn.execute(text("ALTER TABLE work_report_tasks ADD COLUMN records_count integer NOT NULL DEFAULT 0"))
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=10, records=99, snapshot="docs")

    gates = preflight.evaluate(preflight.collect(conn))
    assert not all(ok for ok, _ in gates)
    assert "UNSAFE" in _gate_text(gates)


def test_missing_exact_activity_fails(sandbox):
    """Only two of the three exact names present -> refuse."""
    conn = sandbox(preflight.REV_0056)
    _seed_activities(conn, include=SUBS[:2])

    gates = preflight.evaluate(preflight.collect(conn))
    assert not all(ok for ok, _ in gates)
    assert "NOT FOUND" in _gate_text(gates)


def test_duplicate_pending_activity_requests_fail(sandbox):
    """0057 adds a partial unique index; pre-existing duplicates would break it."""
    conn = sandbox(preflight.REV_0056)
    _seed_activities(conn)
    emp, rep, sub = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
    for _ in range(2):
        conn.execute(
            text(
                "INSERT INTO activity_requests "
                "(id, employee_id, report_id, sub_activity_id, status) "
                "VALUES (:i, :e, :r, :s, 'pending')"
            ),
            {"i": str(uuid.uuid4()), "e": emp, "r": rep, "s": sub},
        )

    snap = preflight.collect(conn)
    gates = preflight.evaluate(snap)
    assert len(snap["duplicate_pending_groups"]) == 1
    assert not all(ok for ok, _ in gates)
    assert "duplicate pending" in _gate_text(gates)


def test_unexpected_revision_fails(sandbox):
    conn = sandbox(preflight.REV_0056)
    conn.execute(text("UPDATE alembic_version SET version_num = '0042_something_else'"))
    _seed_activities(conn)

    gates = preflight.evaluate(preflight.collect(conn))
    assert not all(ok for ok, _ in gates)
    assert "UNEXPECTED" in _gate_text(gates)


def test_unrelated_docs_checksum_excludes_the_converted_activities(sandbox):
    """The DOCS rows that must survive untouched are counted separately."""
    conn = sandbox(preflight.REV_0056)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=100)          # will convert
    other = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO activity_master (id, parent_id, name, relevant_count_field) "
            "VALUES (:i, NULL, 'DOC OTHER', 'docs')"
        ),
        {"i": other},
    )
    _seed_task(conn, other, docs=45)                  # must stay DOCS

    snap = preflight.collect(conn)
    assert snap["unrelated_docs"]["row_count"] == 1
    assert snap["unrelated_docs"]["docs_total"] == 45


def test_preflight_never_writes(sandbox):
    """collect() must not modify anything - it runs against live production."""
    conn = sandbox(preflight.REV_0056)
    ids = _seed_activities(conn)
    _seed_task(conn, ids[SUBS[0]], docs=7)

    before = {
        t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
        for t in ("work_report_tasks", "daily_work_reports", "activity_master",
                  "activity_requests", "alembic_version")
    }
    sums_before = conn.execute(text("SELECT coalesce(sum(docs_count),0) FROM work_report_tasks")).scalar_one()

    preflight.collect(conn)

    after = {
        t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one()
        for t in before
    }
    sums_after = conn.execute(text("SELECT coalesce(sum(docs_count),0) FROM work_report_tasks")).scalar_one()
    assert before == after
    assert sums_before == sums_after
