"""Migration 0060 — work report periods backfill.

The schema half of 0060 is already applied by the normal migration chain
(conftest runs `alembic upgrade head`). These tests seed SYNTHETIC
pre-period rows — reports with no work_report_periods row, task rows with
period_id NULL — and drive the migration's real `backfill(bind)` helper
(0058 precedent), proving:

  * every report gains exactly one legacy Full-Day period;
  * a historical half_day report keeps its effective half benchmark
    (fraction 0.5 + is_legacy_half_day, base = 2 x effective, effective
    untouched) without guessing which half was worked;
  * task rows and activity requests are linked to the new period;
  * the backfill is idempotent (re-running changes nothing).

The upgrade/downgrade DDL itself is rehearsed in
test_migration_downgrade_upgrade_rehearsal.
"""
import importlib.util
import pathlib
import uuid
from datetime import date

import pytest
from sqlalchemy import text

_MIG_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0060_work_report_periods.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig0060", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()


@pytest.fixture()
def seed(db):
    """One employee + project; helpers to plant pre-period reports/tasks/
    requests exactly as the production DB holds them before 0060 runs."""
    emp_id, proj_id = uuid.uuid4(), uuid.uuid4()
    db.execute(text(
        "INSERT INTO employees (id, employee_code, first_name, last_name, status)"
        " VALUES (:id, 'MIG-E1', 'Mig', 'Test', 'active')"
    ), {"id": emp_id})
    db.execute(text(
        "INSERT INTO projects (id, code, name, status)"
        " VALUES (:id, 'MIG-P1', 'Mig Project', 'active')"
    ), {"id": proj_id})

    def make_report(report_date, day_status=None, location=None):
        rid = uuid.uuid4()
        db.execute(text(
            "INSERT INTO daily_work_reports"
            " (id, employee_id, report_date, status, day_status, location)"
            " VALUES (:id, :emp, :d, 'submitted', :ds, :loc)"
        ), {"id": rid, "emp": emp_id, "d": report_date, "ds": day_status, "loc": location})
        return rid

    def make_task(report_id, *, effective=None):
        tid = uuid.uuid4()
        db.execute(text(
            "INSERT INTO work_report_tasks"
            " (id, report_id, project_id, description, benchmark_value_snapshot)"
            " VALUES (:id, :rid, :pid, 'legacy row', :snap)"
        ), {"id": tid, "rid": report_id, "pid": proj_id, "snap": effective})
        return tid

    def make_request(report_id):
        qid = uuid.uuid4()
        db.execute(text(
            "INSERT INTO activity_requests"
            " (id, employee_id, report_id, project_id, sub_activity_id, status)"
            " VALUES (:id, :emp, :rid, :pid, :sub, 'pending')"
        ), {"id": qid, "emp": emp_id, "rid": report_id, "pid": proj_id,
            "sub": _make_sub_activity(db)})
        return qid

    db.commit()
    return {
        "emp_id": emp_id, "proj_id": proj_id,
        "report": make_report, "task": make_task, "request": make_request,
        "db": db,
    }


def _make_sub_activity(db):
    parent, sub = uuid.uuid4(), uuid.uuid4()
    db.execute(text(
        "INSERT INTO activity_master (id, level, name, is_active)"
        " VALUES (:id, 'activity', :n, true)"
    ), {"id": parent, "n": f"MIG-A-{parent.hex[:6]}"})
    db.execute(text(
        "INSERT INTO activity_master (id, parent_id, level, name, is_active)"
        " VALUES (:id, :p, 'sub_activity', :n, true)"
    ), {"id": sub, "p": parent, "n": f"MIG-S-{sub.hex[:6]}"})
    return sub


def _period_rows(db, report_id):
    return db.execute(text(
        "SELECT day_part, period_status, location, work_fraction,"
        " is_legacy_half_day FROM work_report_periods WHERE report_id = :rid"
    ), {"rid": report_id}).mappings().all()


def _run_backfill(db):
    MIG.backfill(db.connection())
    db.commit()


def test_full_day_report_gets_one_period(seed):
    db = seed["db"]
    rid = seed["report"](date(2026, 7, 1), "work_at_office", "chennai")
    tid = seed["task"](rid, effective=250)
    _run_backfill(db)

    periods = _period_rows(db, rid)
    assert len(periods) == 1
    p = periods[0]
    assert p["day_part"] == "full_day"
    assert p["period_status"] == "work_at_office"
    assert p["location"] == "chennai"
    assert float(p["work_fraction"]) == 1.0
    assert p["is_legacy_half_day"] is False

    task = db.execute(text(
        "SELECT period_id, benchmark_value_snapshot, benchmark_base_value_snapshot,"
        " benchmark_fraction_snapshot FROM work_report_tasks WHERE id = :id"
    ), {"id": tid}).mappings().one()
    assert task["period_id"] is not None
    assert float(task["benchmark_value_snapshot"]) == 250.0   # untouched
    assert float(task["benchmark_base_value_snapshot"]) == 250.0
    assert float(task["benchmark_fraction_snapshot"]) == 1.0


def test_half_day_report_keeps_effective_and_marks_legacy(seed):
    db = seed["db"]
    rid = seed["report"](date(2026, 7, 2), "half_day", "chennai")
    tid = seed["task"](rid, effective=60)  # frozen at half of a 120 base
    _run_backfill(db)

    p = _period_rows(db, rid)[0]
    # Deliberately NOT first/second half — the worked half is unknown.
    assert p["day_part"] == "full_day"
    assert float(p["work_fraction"]) == 0.5
    assert p["is_legacy_half_day"] is True

    task = db.execute(text(
        "SELECT benchmark_value_snapshot, benchmark_base_value_snapshot,"
        " benchmark_fraction_snapshot FROM work_report_tasks WHERE id = :id"
    ), {"id": tid}).mappings().one()
    assert float(task["benchmark_value_snapshot"]) == 60.0    # preserved
    assert float(task["benchmark_base_value_snapshot"]) == 120.0
    assert float(task["benchmark_fraction_snapshot"]) == 0.5


def test_null_day_status_and_unsnapshotted_rows(seed):
    db = seed["db"]
    rid = seed["report"](date(2026, 7, 3))  # day_status NULL (very old rows)
    tid = seed["task"](rid, effective=None)  # never submitted with a benchmark
    _run_backfill(db)

    p = _period_rows(db, rid)[0]
    assert p["period_status"] is None
    assert float(p["work_fraction"]) == 1.0
    task = db.execute(text(
        "SELECT period_id, benchmark_base_value_snapshot, benchmark_fraction_snapshot"
        " FROM work_report_tasks WHERE id = :id"
    ), {"id": tid}).mappings().one()
    assert task["period_id"] is not None
    # No effective snapshot -> no derived base/fraction invented.
    assert task["benchmark_base_value_snapshot"] is None
    assert task["benchmark_fraction_snapshot"] is None


def test_activity_request_linked_to_report_period(seed):
    db = seed["db"]
    rid = seed["report"](date(2026, 7, 4), "work_at_office")
    qid = seed["request"](rid)
    _run_backfill(db)
    got = db.execute(text(
        "SELECT a.period_id, p.report_id FROM activity_requests a"
        " JOIN work_report_periods p ON p.id = a.period_id WHERE a.id = :id"
    ), {"id": qid}).mappings().one()
    assert got["report_id"] == rid


def test_backfill_is_idempotent(seed):
    db = seed["db"]
    rid = seed["report"](date(2026, 7, 5), "half_day")
    tid = seed["task"](rid, effective=60)
    _run_backfill(db)
    _run_backfill(db)  # second run must be a no-op

    assert len(_period_rows(db, rid)) == 1
    task = db.execute(text(
        "SELECT benchmark_base_value_snapshot FROM work_report_tasks WHERE id = :id"
    ), {"id": tid}).mappings().one()
    # Not doubled to 240 by the re-run.
    assert float(task["benchmark_base_value_snapshot"]) == 120.0


def test_migration_downgrade_upgrade_rehearsal(db):
    """The DDL is reversible: walk the schema down to 0059 and back to head
    against the live test database. Runs LAST in this file (fresh tables are
    recreated; _clean_state truncates per test so no data survives anyway)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    db.close()  # release our connection so DDL doesn't deadlock
    command.downgrade(cfg, "0059_activity_req_pages_records")
    command.upgrade(cfg, "head")
    with db.bind.connect() as conn:
        assert conn.execute(text(
            "SELECT count(*) FROM information_schema.tables"
            " WHERE table_name = 'work_report_periods'"
        )).scalar_one() == 1
