"""Migration 0058 — PAGES/RECORDS units + the DOCS -> RECORDS conversion.

The local database holds ZERO historical report rows for the six affected
sub-activities, but production may hold many. So every case below is proved
against SYNTHETIC historical rows seeded here, exercising the migration's real
helpers (`_resolve_sub_activity_ids`, `migrate_docs_to_records`) rather than a
reimplementation of them.

The schema half of 0058 is already applied to the test database by the normal
migration chain (conftest runs `alembic upgrade head`), so these tests seed data
on top of it and drive the data half directly. `_clean_state` truncates
activity_master / work_report_tasks between tests, so each case starts empty.

Naming matters here: selection is by exact trimmed (parent name, sub-activity
name), never by UUID and never by partial match. `test_only_the_three_exact_sub_activities_migrate`
and `test_unrelated_docs_activity_untouched` are the guards on that.
"""
import importlib.util
import pathlib
import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

_MIG_PATH = (
    pathlib.Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "0058_pages_records_units.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("mig0058", _MIG_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MIG = _load_migration()

# The three approved RECORDS sub-activities, verbatim.
CONSOLIDATION = "DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)"
FILE_PATH_POP = (
    "DOC IDB-DOC FILE PATH/POPULATION OF DOC.NO/DWG NO/TITLE/DOC.TYPE AND "
    "ORGANISING DOC.TYPE FOLDER IF MDR/VDR NOT AVAILABLE"
)
FILE_PATH_MIG = "DOC IDB-DOC FILE PATH MIGRATION WITH MDR/VDR AND MANUAL MATCHING"
# Genuinely document-based siblings under the SAME parent — must never convert.
QC = "DOC IDB-QC"
REWORK = "DOC IDB-REWORK"


class Seeder:
    """Minimal synthetic fixture: one employee, one project, one report, plus
    whatever activity_master rows and work_report_tasks rows a test needs."""

    def __init__(self, db):
        self.db = db
        self.employee_id = uuid.uuid4()
        self.project_id = uuid.uuid4()
        self.report_id = uuid.uuid4()
        db.execute(
            text(
                "INSERT INTO employees (id, employee_code, first_name, last_name) "
                "VALUES (:id, 'PR-1', 'Pages', 'Records')"
            ),
            {"id": self.employee_id},
        )
        db.execute(
            text("INSERT INTO projects (id, code, name) VALUES (:id, 'PR-P', 'Proj')"),
            {"id": self.project_id},
        )
        db.execute(
            text(
                "INSERT INTO daily_work_reports (id, employee_id, report_date, status) "
                "VALUES (:id, :emp, :d, 'submitted')"
            ),
            {"id": self.report_id, "emp": self.employee_id, "d": date(2026, 7, 15)},
        )
        self.parents: dict = {}

    def parent(self, name: str) -> uuid.UUID:
        if name not in self.parents:
            pid = uuid.uuid4()
            self.db.execute(
                text(
                    "INSERT INTO activity_master (id, name, level, is_active) "
                    "VALUES (:id, :name, 'activity', true)"
                ),
                {"id": pid, "name": name},
            )
            self.parents[name] = pid
        return self.parents[name]

    def sub(
        self,
        parent_name: str,
        name: str,
        *,
        is_active: bool = True,
        benchmark_type: str | None = "NUMERIC",
        benchmark_value: float | None = 100,
        unit: str | None = "docs",
        period_days: int | None = 1,
    ) -> uuid.UUID:
        sid = uuid.uuid4()
        self.db.execute(
            text(
                "INSERT INTO activity_master "
                "(id, parent_id, name, level, is_active, benchmark_type, "
                " benchmark_value, benchmark_period_days, relevant_count_field) "
                "VALUES (:id, :pid, :name, 'sub_activity', :active, :bt, :bv, :pd, :unit)"
            ),
            {
                "id": sid,
                "pid": self.parent(parent_name),
                "name": name,
                "active": is_active,
                "bt": benchmark_type,
                "bv": benchmark_value,
                "pd": period_days,
                "unit": unit,
            },
        )
        return sid

    def task(
        self,
        sub_id: uuid.UUID,
        *,
        docs: int = 0,
        records: int = 0,
        tags: int = 0,
        snapshot: str | None = "docs",
        benchmark_value_snapshot: float | None = 1000,
        deficit: float | None = 150,
        productivity_pct: float | None = 85,
    ) -> uuid.UUID:
        tid = uuid.uuid4()
        self.db.execute(
            text(
                "INSERT INTO work_report_tasks "
                "(id, report_id, project_id, description, sub_activity_id, "
                " tags_count, docs_count, bom_count, spares_count, pages_count, "
                " records_count, relevant_count_field_snapshot, "
                " benchmark_value_snapshot, benchmark_period_days_snapshot, "
                " deficit, productivity_pct) "
                "VALUES (:id, :rid, :pid, 'synthetic', :sub, :tags, :docs, 0, 0, 0, "
                "        :records, :snap, :bvs, 1, :def, :prod)"
            ),
            {
                "id": tid,
                "rid": self.report_id,
                "pid": self.project_id,
                "sub": sub_id,
                "tags": tags,
                "docs": docs,
                "records": records,
                "snap": snapshot,
                "bvs": benchmark_value_snapshot,
                "def": deficit,
                "prod": productivity_pct,
            },
        )
        return tid

    def read(self, task_id: uuid.UUID):
        return self.db.execute(
            text(
                "SELECT t.docs_count, t.records_count, t.tags_count, "
                "       t.relevant_count_field_snapshot, t.benchmark_value_snapshot, "
                "       t.benchmark_period_days_snapshot, t.deficit, t.productivity_pct, "
                "       t.report_id, t.project_id, t.sub_activity_id, t.is_completed, "
                "       r.employee_id, r.report_date "
                "FROM work_report_tasks t "
                "JOIN daily_work_reports r ON r.id = t.report_id "
                "WHERE t.id = :id"
            ),
            {"id": task_id},
        ).one()

    def resolve_records(self):
        return MIG._flatten(
            MIG._resolve_sub_activity_ids(
                self.db.connection(), "DOC IDB", MIG._RECORDS_TARGETS.keys()
            )
        )

    def run(self):
        return MIG.migrate_docs_to_records(self.db.connection(), self.resolve_records())


@pytest.fixture()
def seed(db):
    s = Seeder(db)
    yield s
    db.rollback()


def test_1_normal_historical_migration(seed):
    """docs_count = 850 on an approved RECORDS sub-activity moves wholesale to
    records_count, and the frozen unit snapshot follows it. Every value that
    feeds a historical achievement/pending figure must survive untouched."""
    sub = seed.sub("DOC IDB", CONSOLIDATION, benchmark_value=1000)
    task = seed.task(sub, docs=850, records=0, snapshot="docs")

    stats = seed.run()

    row = seed.read(task)
    assert row.docs_count == 0
    assert row.records_count == 850
    assert row.relevant_count_field_snapshot == "records"
    # The historical performance record is numerically unchanged.
    assert row.benchmark_value_snapshot == 1000
    assert row.benchmark_period_days_snapshot == 1
    assert row.deficit == 150
    assert row.productivity_pct == 85
    assert row.report_id == seed.report_id
    assert row.project_id == seed.project_id
    assert row.sub_activity_id == sub
    assert stats["moved_rows"] == 1
    assert stats["docs_before"] == 850
    assert stats["records_after"] == 850


def test_2_unrelated_docs_activity_untouched(seed):
    """DOC IDB-QC shares the exact parent and the 'DOC IDB-' prefix but is a
    genuinely document-based activity. Any prefix/ILIKE matching would sweep it
    up; exact-name matching must not."""
    records_sub = seed.sub("DOC IDB", CONSOLIDATION)
    qc_sub = seed.sub("DOC IDB", QC, benchmark_value=500)
    rework_sub = seed.sub("DOC IDB", REWORK, benchmark_value=500)
    moved = seed.task(records_sub, docs=300)
    qc_task = seed.task(qc_sub, docs=500, snapshot="docs")
    rework_task = seed.task(rework_sub, docs=250, snapshot="docs")

    seed.run()

    assert seed.read(moved).records_count == 300
    for untouched in (qc_task, rework_task):
        row = seed.read(untouched)
        assert row.records_count == 0
        assert row.relevant_count_field_snapshot == "docs"
    assert seed.read(qc_task).docs_count == 500
    assert seed.read(rework_task).docs_count == 250
    # The sub-activity config of the unrelated rows is untouched too.
    for sid in (qc_sub, rework_sub):
        cfg = seed.db.execute(
            text("SELECT relevant_count_field FROM activity_master WHERE id = :id"),
            {"id": sid},
        ).one()
        assert cfg.relevant_count_field == "docs"


def test_3_inactive_historical_duplicate_with_reports_migrates(seed):
    """An inactive duplicate carrying the exact parent + exact name still owns
    real history, so its rows must convert too — otherwise a re-exported old
    report would read under the wrong unit."""
    active = seed.sub("DOC IDB", CONSOLIDATION)
    dupe = seed.sub("DOC IDB", CONSOLIDATION, is_active=False)
    active_task = seed.task(active, docs=100)
    dupe_task = seed.task(dupe, docs=700)

    resolved = seed.resolve_records()
    assert set(resolved) == {active, dupe}

    seed.run()

    assert seed.read(active_task).records_count == 100
    assert seed.read(dupe_task).records_count == 700
    assert seed.read(dupe_task).docs_count == 0


def test_3b_inactive_duplicate_without_reports_is_not_resolved(seed):
    """The other half of the rule: an unused inactive duplicate has no history
    to keep consistent and is left alone."""
    active = seed.sub("DOC IDB", CONSOLIDATION)
    unused_dupe = seed.sub("DOC IDB", CONSOLIDATION, is_active=False)

    resolved = seed.resolve_records()

    assert resolved == [active]
    assert unused_dupe not in resolved


def test_4_already_migrated_row_is_a_noop(seed):
    """docs = 0, records = 400 -> nothing moves and nothing is added."""
    sub = seed.sub("DOC IDB", FILE_PATH_MIG, benchmark_value=400)
    task = seed.task(sub, docs=0, records=400, snapshot="records")

    stats = seed.run()

    row = seed.read(task)
    assert row.docs_count == 0
    assert row.records_count == 400
    assert row.relevant_count_field_snapshot == "records"
    assert stats["moved_rows"] == 0


def test_5_zero_count_row_realigns_snapshot_only(seed):
    """docs = 0, records = 0 -> no quantity movement, but the row still reported
    against RECORDS, so its frozen unit snapshot is realigned."""
    sub = seed.sub("DOC IDB", FILE_PATH_POP, benchmark_value=250)
    task = seed.task(sub, docs=0, records=0, snapshot="docs")

    stats = seed.run()

    row = seed.read(task)
    assert row.docs_count == 0
    assert row.records_count == 0
    assert row.relevant_count_field_snapshot == "records"
    assert stats["moved_rows"] == 0
    assert stats["resnapshotted_rows"] == 1


def test_6_conflict_aborts_and_changes_nothing(seed):
    """docs = 100 AND records = 50 is unresolvable: moving would overwrite, and
    adding would invent a number. Abort with the exact task id, touch nothing."""
    sub = seed.sub("DOC IDB", CONSOLIDATION)
    conflict = seed.task(sub, docs=100, records=50)
    innocent = seed.task(sub, docs=900, records=0)

    with pytest.raises(RuntimeError) as exc:
        seed.run()

    message = str(exc.value)
    assert str(conflict) in message  # the exact offending row is named
    assert "0058 aborted" in message
    # Nothing moved — not the conflict row, and not the valid row beside it.
    row = seed.read(conflict)
    assert (row.docs_count, row.records_count) == (100, 50)
    other = seed.read(innocent)
    assert (other.docs_count, other.records_count) == (900, 0)


def test_7_rerun_is_idempotent(seed):
    """Running the reconciliation a second time must not move data twice, must
    not double a count, and must not error."""
    sub = seed.sub("DOC IDB", CONSOLIDATION)
    task = seed.task(sub, docs=850, records=0)

    seed.run()
    first = seed.read(task)
    assert (first.docs_count, first.records_count) == (0, 850)

    # Two further passes: the count must neither double nor drift.
    seed.run()
    stats = seed.run()

    again = seed.read(task)
    assert (again.docs_count, again.records_count) == (0, 850)
    assert again.relevant_count_field_snapshot == "records"
    assert stats["moved_rows"] == 0
    assert stats["resnapshotted_rows"] == 0


def test_only_the_three_exact_sub_activities_migrate(seed):
    """The complete selection proof: three approved names under DOC IDB convert;
    two document-based siblings under the same parent, and an identically-named
    sub-activity under a DIFFERENT parent, do not."""
    approved = {
        name: seed.sub("DOC IDB", name)
        for name in (CONSOLIDATION, FILE_PATH_POP, FILE_PATH_MIG)
    }
    qc = seed.sub("DOC IDB", QC)
    rework = seed.sub("DOC IDB", REWORK)
    # Same leaf name, wrong parent -> must not resolve.
    impostor = seed.sub("BOM IDB", CONSOLIDATION)

    resolved = set(seed.resolve_records())

    assert resolved == set(approved.values())
    assert qc not in resolved
    assert rework not in resolved
    assert impostor not in resolved


def test_unrelated_docs_sum_invariant_holds(seed):
    """The migration's own invariant: DOCS belonging to anything else is
    conserved exactly."""
    records_sub = seed.sub("DOC IDB", CONSOLIDATION)
    qc_sub = seed.sub("DOC IDB", QC)
    seed.task(records_sub, docs=500)
    seed.task(qc_sub, docs=400)
    seed.task(qc_sub, docs=100)

    stats = seed.run()

    assert stats["unrelated_docs_sum"] == 500
    total_docs = seed.db.execute(
        text("SELECT coalesce(sum(docs_count), 0) AS d FROM work_report_tasks")
    ).one().d
    assert total_docs == 500  # only QC's DOCS remain


def test_no_rows_created_or_deleted(seed):
    sub = seed.sub("DOC IDB", CONSOLIDATION)
    for n in (100, 200, 0):
        seed.task(sub, docs=n)
    before = seed.db.execute(text("SELECT count(*) AS n FROM work_report_tasks")).one().n

    seed.run()

    after = seed.db.execute(text("SELECT count(*) AS n FROM work_report_tasks")).one().n
    assert before == after == 3


def test_empty_database_is_a_noop(seed):
    """A database that never loaded the master data (a fresh test DB, a new
    office) resolves to nothing and the migration must still succeed."""
    assert seed.resolve_records() == []
    stats = seed.run()
    assert stats["matching_rows"] == 0
    assert stats["moved_rows"] == 0


# --- Test 8: model / constraint acceptance ---------------------------------


@pytest.mark.parametrize("unit", ["tags", "docs", "bom", "spares", "pages", "records"])
def test_8_all_six_units_accepted(seed, unit):
    seed.sub("MTL", f"UNIT {unit}", benchmark_type="NUMERIC_DAILY", unit=unit)
    seed.db.flush()


def test_8_invalid_unit_rejected(seed):
    with pytest.raises(IntegrityError) as exc:
        seed.sub("MTL", "BAD UNIT", benchmark_type="NUMERIC_DAILY", unit="sheets")
        seed.db.flush()
    assert "activity_master_relevant_count_field_valid" in str(exc.value)


@pytest.mark.parametrize(
    "mode", ["NUMERIC_DAILY", "TASK_STATUS_ONLY", "TASK_WITH_QUANTITY"]
)
def test_8_new_benchmark_modes_accepted(seed, mode):
    # TASK_STATUS_ONLY carries no quantity; the other two do.
    quantity = mode != "TASK_STATUS_ONLY"
    seed.sub(
        "MTL",
        f"MODE {mode}",
        benchmark_type=mode,
        benchmark_value=500 if quantity else None,
        unit="pages" if quantity else None,
    )
    seed.db.flush()


@pytest.mark.parametrize("mode", ["NUMERIC", "TASK_BASED"])
def test_8_legacy_benchmark_modes_still_accepted(seed, mode):
    """Historical rows must keep working — 0058 never rewrites them."""
    quantity = mode == "NUMERIC"
    seed.sub(
        "MTL",
        f"LEGACY {mode}",
        benchmark_type=mode,
        benchmark_value=250 if quantity else None,
        unit="docs" if quantity else None,
    )
    seed.db.flush()


def test_8_invalid_benchmark_mode_rejected(seed):
    with pytest.raises(IntegrityError) as exc:
        seed.sub("MTL", "BAD MODE", benchmark_type="SOMETHING_ELSE")
        seed.db.flush()
    assert "activity_master_benchmark_type_valid" in str(exc.value)


@pytest.mark.parametrize("mode", ["NUMERIC", "NUMERIC_DAILY", "TASK_WITH_QUANTITY"])
def test_8_quantity_modes_require_a_target(seed, mode):
    with pytest.raises(IntegrityError) as exc:
        seed.sub("MTL", f"NO TARGET {mode}", benchmark_type=mode,
                 benchmark_value=None, unit="pages")
        seed.db.flush()
    assert "activity_master_numeric_requires_value" in str(exc.value)


@pytest.mark.parametrize("mode", ["NUMERIC", "NUMERIC_DAILY", "TASK_WITH_QUANTITY"])
def test_8_quantity_modes_require_a_unit(seed, mode):
    with pytest.raises(IntegrityError) as exc:
        seed.sub("MTL", f"NO UNIT {mode}", benchmark_type=mode,
                 benchmark_value=500, unit=None)
        seed.db.flush()
    assert "activity_master_numeric_requires_count_field" in str(exc.value)


def test_8_task_status_only_needs_neither_target_nor_unit(seed):
    seed.sub(
        "MTL", "STATUS ONLY", benchmark_type="TASK_STATUS_ONLY",
        benchmark_value=None, unit=None,
    )
    seed.db.flush()


def test_8_no_benchmark_row_still_allowed(seed):
    seed.sub(
        "MTL", "NO BENCHMARK", benchmark_type=None,
        benchmark_value=None, unit=None, period_days=None,
    )
    seed.db.flush()


def test_8_pages_and_records_counts_default_to_zero(seed):
    """The new columns follow tags/docs/bom/spares exactly: NOT NULL DEFAULT 0,
    so an unused unit is 0 rather than NULL."""
    sub = seed.sub("MTL", "DEFAULTS")
    tid = uuid.uuid4()
    seed.db.execute(
        text(
            "INSERT INTO work_report_tasks (id, report_id, project_id, description, "
            "sub_activity_id) VALUES (:id, :rid, :pid, 'defaults', :sub)"
        ),
        {"id": tid, "rid": seed.report_id, "pid": seed.project_id, "sub": sub},
    )
    row = seed.db.execute(
        text(
            "SELECT pages_count, records_count FROM work_report_tasks WHERE id = :id"
        ),
        {"id": tid},
    ).one()
    assert (row.pages_count, row.records_count) == (0, 0)


def test_8_pages_and_records_counts_are_not_nullable(seed):
    sub = seed.sub("MTL", "NOT NULL")
    with pytest.raises(IntegrityError):
        seed.db.execute(
            text(
                "INSERT INTO work_report_tasks (id, report_id, project_id, "
                "description, sub_activity_id, pages_count) "
                "VALUES (:id, :rid, :pid, 'x', :sub, NULL)"
            ),
            {"id": uuid.uuid4(), "rid": seed.report_id, "pid": seed.project_id,
             "sub": sub},
        )
        seed.db.flush()
