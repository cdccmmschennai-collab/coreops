"""Phase 2 — PAGES/RECORDS units and the benchmark mode split, end to end
through the API (schemas -> services -> benchmark calculations).

Covers the two things Phase 1 could not: that the new units survive the whole
create/read/update round trip rather than just existing as columns, and that the
five benchmark modes behave per their contract while the two legacy values keep
working untouched.

The unit-isolation tests are the important ones: PAGES must never offset RECORDS
and RECORDS must never offset DOCS. Those are the guarantees that make a
per-sub-activity achievement figure meaningful.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.activity_master.models import (
    COUNT_FIELD_BY_UNIT,
    DAILY_QUANTITY_BENCHMARK_TYPES,
    QUANTITY_BENCHMARK_TYPES,
    TASK_BENCHMARK_TYPES,
)
from app.modules.activity_master.service import compute_benchmark
from app.modules.projects.models import ProjectStatus
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
AM = "/api/v1/activity-master"
TODAY_D = date.today()
TODAY = TODAY_D.isoformat()


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def activity_admin(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _make_sub(client, admin_header, *, activity_name="MTL", name="Sub", **body):
    a = client.post(
        f"{AM}/activities", json={"name": activity_name}, headers=admin_header
    ).json()
    res = client.post(
        f"{AM}/activities/{a['id']}/sub-activities",
        json={"name": name, **body},
        headers=admin_header,
    )
    assert res.status_code in (200, 201), res.text
    return a, res.json()


def _submit(client, header, project_id, tasks, report_date=TODAY):
    created = client.post(
        BASE, headers=header, json={"report_date": report_date, "tasks": tasks}
    ).json()
    submitted = client.post(
        f"{BASE}/{created['id']}/submit", headers=header
    ).json()
    return created, submitted


# ── the shared unit mapping ────────────────────────────────────────────────


def test_all_six_units_map_to_a_real_column():
    from app.modules.work_reports.models import WorkReportTask

    assert set(COUNT_FIELD_BY_UNIT) == {
        "tags", "docs", "bom", "spares", "pages", "records"
    }
    for unit, column in COUNT_FIELD_BY_UNIT.items():
        assert hasattr(WorkReportTask, column), f"{unit} -> {column} is not a column"


def test_ledger_and_task_sources_stay_disjoint():
    """The benchmark export merges the daily ledger with the task lumpsum query
    and relies on them never selecting the same row. TASK_WITH_QUANTITY is the
    trap: it is a QUANTITY mode but must be exported via the task side only."""
    assert DAILY_QUANTITY_BENCHMARK_TYPES & TASK_BENCHMARK_TYPES == set()
    assert "TASK_WITH_QUANTITY" in QUANTITY_BENCHMARK_TYPES
    assert "TASK_WITH_QUANTITY" in TASK_BENCHMARK_TYPES
    assert "TASK_WITH_QUANTITY" not in DAILY_QUANTITY_BENCHMARK_TYPES
    assert DAILY_QUANTITY_BENCHMARK_TYPES == {"NUMERIC", "NUMERIC_DAILY"}


# ── compute_benchmark across the modes ─────────────────────────────────────


@pytest.mark.parametrize("mode", ["NUMERIC", "NUMERIC_DAILY", "TASK_WITH_QUANTITY"])
def test_quantity_modes_compute_pending_and_percentage(mode):
    deficit, pct = compute_benchmark(mode, Decimal("500"), 400)
    assert deficit == Decimal("100")  # max(0, 500 - 400)
    assert pct == Decimal("80")


@pytest.mark.parametrize("mode", ["TASK_BASED", "TASK_STATUS_ONLY"])
def test_status_only_modes_never_compute(mode):
    assert compute_benchmark(mode, None, 100) == (None, None)
    # Even handed a value, a status-only task produces no numeric percentage.
    assert compute_benchmark(mode, Decimal("500"), 400) == (None, None)


def test_pages_pending_is_clamped_at_zero():
    deficit, pct = compute_benchmark("TASK_WITH_QUANTITY", Decimal("500"), 620)
    assert deficit == Decimal("0")  # never negative
    assert pct == Decimal("124")    # uncapped


def test_records_pending_calculation():
    deficit, pct = compute_benchmark("NUMERIC_DAILY", Decimal("1000"), 850)
    assert deficit == Decimal("150")
    assert pct == Decimal("85")


def test_legacy_numeric_and_new_numeric_daily_behave_identically():
    assert compute_benchmark("NUMERIC", Decimal("250"), 200) == compute_benchmark(
        "NUMERIC_DAILY", Decimal("250"), 200
    )


# ── Activity Master API ────────────────────────────────────────────────────


def test_flat_sub_activity_api_returns_remarks_and_unit_note(client, activity_admin):
    """The exact data path that was broken: the report form's flat endpoint
    dropped benchmark_remarks/benchmark_unit_note, so configured guidance such
    as '500 REQUIRED PAGES/DAY' never reached the employee."""
    _make_sub(
        client, activity_admin, name="MTL-DOC.O&M MANNUALS DATA POPULATION",
        benchmark_type="TASK_WITH_QUANTITY", benchmark_value=500,
        benchmark_period_days=1, relevant_count_field="pages",
        benchmark_unit_note="PAGES", benchmark_remarks="500 REQUIRED PAGES/DAY",
    )
    rows = client.get(f"{AM}/sub-activities", headers=activity_admin).json()
    row = next(r for r in rows if r["name"].startswith("MTL-DOC.O&M"))

    assert row["benchmark_remarks"] == "500 REQUIRED PAGES/DAY"
    assert row["benchmark_unit_note"] == "PAGES"
    assert row["benchmark_type"] == "TASK_WITH_QUANTITY"
    assert float(row["benchmark_value"]) == 500.0
    assert row["benchmark_period_days"] == 1
    assert row["relevant_count_field"] == "pages"


def test_flat_sub_activity_api_keeps_empty_remarks_null(client, activity_admin):
    """An unconfigured remark must stay null so the UI can decide not to render
    an empty guidance panel."""
    _make_sub(
        client, activity_admin, name="NO GUIDANCE",
        benchmark_type="TASK_STATUS_ONLY",
    )
    rows = client.get(f"{AM}/sub-activities", headers=activity_admin).json()
    row = next(r for r in rows if r["name"] == "NO GUIDANCE")
    assert row["benchmark_remarks"] is None
    assert row["benchmark_unit_note"] is None


@pytest.mark.parametrize("unit", ["pages", "records"])
def test_new_units_configurable_via_api(client, activity_admin, unit):
    _, sub = _make_sub(
        client, activity_admin, name=f"CFG {unit}",
        benchmark_type="NUMERIC_DAILY", benchmark_value=250,
        relevant_count_field=unit,
    )
    assert sub["relevant_count_field"] == unit


def test_invalid_unit_rejected_by_api(client, activity_admin):
    a = client.post(f"{AM}/activities", json={"name": "X"}, headers=activity_admin).json()
    res = client.post(
        f"{AM}/activities/{a['id']}/sub-activities",
        json={"name": "BAD", "benchmark_type": "NUMERIC_DAILY",
              "benchmark_value": 10, "relevant_count_field": "sheets"},
        headers=activity_admin,
    )
    assert res.status_code == 422


@pytest.mark.parametrize("mode", ["NUMERIC_DAILY", "TASK_WITH_QUANTITY"])
def test_quantity_modes_require_value_and_unit_via_api(client, activity_admin, mode):
    a = client.post(f"{AM}/activities", json={"name": f"X{mode}"}, headers=activity_admin).json()
    res = client.post(
        f"{AM}/activities/{a['id']}/sub-activities",
        json={"name": "NO TARGET", "benchmark_type": mode},
        headers=activity_admin,
    )
    assert res.status_code == 422


def test_task_status_only_needs_no_target_via_api(client, activity_admin):
    _, sub = _make_sub(
        client, activity_admin, name="STATUS ONLY", benchmark_type="TASK_STATUS_ONLY",
        benchmark_period_days=1,
    )
    assert sub["benchmark_type"] == "TASK_STATUS_ONLY"
    assert sub["benchmark_value"] is None


# ── report round trip ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "field,unit,target,actual,expect_deficit,expect_pct",
    [
        ("pages_count", "pages", 500, 400, 100.0, 80.0),
        ("records_count", "records", 1000, 850, 150.0, 85.0),
    ],
)
def test_new_unit_report_round_trip_and_benchmark(
    client, setup_author, activity_admin, field, unit, target, actual,
    expect_deficit, expect_pct,
):
    """Page/record counts are accepted, persisted, returned, and drive the
    benchmark off the configured unit."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name=f"NUM {unit}",
        benchmark_type="NUMERIC_DAILY", benchmark_value=target,
        relevant_count_field=unit,
    )
    created, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"], field: actual}],
    )
    assert created["tasks"][0][field] == actual  # accepted + read back on draft

    task = submitted["tasks"][0]
    assert task[field] == actual
    assert task["relevant_count_field_snapshot"] == unit
    assert float(task["deficit"]) == expect_deficit
    assert float(task["productivity_pct"]) == expect_pct


def test_new_units_survive_update(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="UPD", benchmark_type="NUMERIC_DAILY",
        benchmark_value=500, relevant_count_field="pages",
    )
    created = client.post(
        BASE, headers=a["header"],
        json={"report_date": TODAY, "tasks": [{
            "project_id": str(a["project"].id), "description": "w",
            "sub_activity_id": sub["id"], "pages_count": 100, "records_count": 7,
        }]},
    ).json()
    res = client.patch(
        f"{BASE}/{created['id']}", headers=a["header"],
        json={"tasks": [{
            "project_id": str(a["project"].id), "description": "w",
            "sub_activity_id": sub["id"], "pages_count": 450, "records_count": 9,
        }]},
    )
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated["tasks"][0]["pages_count"] == 450
    assert updated["tasks"][0]["records_count"] == 9

    # And they survive the re-read, not just the write response.
    reread = client.get(f"{BASE}/{created['id']}", headers=a["header"]).json()
    assert reread["tasks"][0]["pages_count"] == 450
    assert reread["tasks"][0]["records_count"] == 9


def test_pages_does_not_offset_records(client, setup_author, activity_admin):
    """A PAGES benchmark reads pages_count ONLY. Records entered on the same row
    must not count toward it."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="PAGES ONLY", benchmark_type="NUMERIC_DAILY",
        benchmark_value=500, relevant_count_field="pages",
    )
    _, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"],
          "pages_count": 200, "records_count": 300}],
    )
    task = submitted["tasks"][0]
    # 200 pages against a 500 target -> 300 short. The 300 records are ignored.
    assert float(task["deficit"]) == 300.0
    assert float(task["productivity_pct"]) == 40.0
    assert task["records_count"] == 300  # stored, just not counted here


def test_records_does_not_offset_docs(client, setup_author, activity_admin):
    """A RECORDS benchmark reads records_count ONLY — a document is not a
    record."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, activity_name="DOC IDB", name="RECORDS ONLY",
        benchmark_type="NUMERIC_DAILY", benchmark_value=1000,
        relevant_count_field="records",
    )
    _, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"],
          "records_count": 400, "docs_count": 600}],
    )
    task = submitted["tasks"][0]
    assert float(task["deficit"]) == 600.0   # 1000 - 400, docs ignored
    assert float(task["productivity_pct"]) == 40.0


def test_unrelated_docs_activity_still_calculates_from_docs(
    client, setup_author, activity_admin
):
    """DOC IDB-QC stays document-based: its benchmark must still read
    docs_count, not records_count."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, activity_name="DOC IDB", name="DOC IDB-QC",
        benchmark_type="NUMERIC", benchmark_value=500, relevant_count_field="docs",
    )
    _, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"],
          "docs_count": 500, "records_count": 0}],
    )
    task = submitted["tasks"][0]
    assert task["relevant_count_field_snapshot"] == "docs"
    assert float(task["deficit"]) == 0.0
    assert float(task["productivity_pct"]) == 100.0


@pytest.mark.parametrize(
    "unit,field", [("tags", "tags_count"), ("docs", "docs_count"),
                   ("bom", "bom_count"), ("spares", "spares_count")]
)
def test_existing_four_units_do_not_regress(
    client, setup_author, activity_admin, unit, field
):
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name=f"OLD {unit}", benchmark_type="NUMERIC",
        benchmark_value=250, relevant_count_field=unit,
    )
    _, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"], field: 200}],
    )
    task = submitted["tasks"][0]
    assert float(task["deficit"]) == 50.0
    assert float(task["productivity_pct"]) == 80.0


# ── TASK_WITH_QUANTITY: quantity AND completion ────────────────────────────


def test_task_with_quantity_has_due_date_and_computes_quantity(
    client, setup_author, activity_admin
):
    """The mode that resolves the contradiction: a real deadline AND a real
    quantity on the same row."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="MTL-DOC.O&M MANNUALS DATA POPULATION",
        benchmark_type="TASK_WITH_QUANTITY", benchmark_value=500,
        benchmark_period_days=1, relevant_count_field="pages",
        benchmark_remarks="500 REQUIRED PAGES/DAY",
    )
    created, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"], "pages_count": 400}],
    )
    # Task side: a server-computed due date exists.
    assert created["tasks"][0]["started_date"] == TODAY
    assert created["tasks"][0]["due_date"] == TODAY
    # Quantity side: real numeric performance.
    task = submitted["tasks"][0]
    assert task["benchmark_type_snapshot"] == "TASK_WITH_QUANTITY"
    assert float(task["deficit"]) == 100.0
    assert float(task["productivity_pct"]) == 80.0


def test_entering_pages_does_not_auto_complete_the_task(
    client, setup_author, activity_admin
):
    """Even at 100% of the daily quantity, the task stays OPEN. The checkbox
    means 'the whole task is finished', never 'today's number is met'."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="PAGES TASK",
        benchmark_type="TASK_WITH_QUANTITY", benchmark_value=500,
        benchmark_period_days=1, relevant_count_field="pages",
    )
    _, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"], "pages_count": 500}],
    )
    task = submitted["tasks"][0]
    assert task["pages_count"] == 500
    assert float(task["productivity_pct"]) == 100.0
    assert task["is_completed"] is False       # NOT inferred from the quantity
    assert task["completed_date"] is None


def test_task_with_quantity_stays_open_when_unchecked(
    client, setup_author, activity_admin
):
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="OPEN TASK",
        benchmark_type="TASK_WITH_QUANTITY", benchmark_value=500,
        benchmark_period_days=1, relevant_count_field="pages",
    )
    created, _ = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"], "pages_count": 200,
          "is_completed": False}],
    )
    assert created["tasks"][0]["is_completed"] is False
    assert created["tasks"][0]["completed_date"] is None


def test_task_with_quantity_closes_only_when_explicitly_completed(
    client, setup_author, activity_admin
):
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="CLOSE TASK",
        benchmark_type="TASK_WITH_QUANTITY", benchmark_value=500,
        benchmark_period_days=1, relevant_count_field="pages",
    )
    created = client.post(
        BASE, headers=a["header"],
        json={"report_date": TODAY, "tasks": [{
            "project_id": str(a["project"].id), "description": "w",
            "sub_activity_id": sub["id"], "pages_count": 500,
            "is_completed": True,
        }]},
    ).json()
    task = created["tasks"][0]
    assert task["is_completed"] is True
    assert task["completed_date"] == TODAY


def test_task_status_only_has_due_date_but_no_percentage(
    client, setup_author, activity_admin
):
    """FINISH WITHIN A DAY / FINISHED / NO PENDING — duration and completion,
    excluded from every numeric percentage and subtotal."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="STATUS TASK",
        benchmark_type="TASK_STATUS_ONLY", benchmark_period_days=1,
    )
    created, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"]}],
    )
    assert created["tasks"][0]["due_date"] == TODAY   # duration tracked
    task = submitted["tasks"][0]
    assert task["deficit"] is None                    # no numeric percentage
    assert task["productivity_pct"] is None


def test_legacy_task_based_still_tracks_completion(
    client, setup_author, activity_admin
):
    """Historical rows using the legacy value must keep their exact behaviour."""
    a = setup_author()
    _, sub = _make_sub(
        client, activity_admin, name="LEGACY TASK", benchmark_type="TASK_BASED",
        benchmark_period_days=1,
    )
    created, submitted = _submit(
        client, a["header"], a["project"].id,
        [{"project_id": str(a["project"].id), "description": "w",
          "sub_activity_id": sub["id"]}],
    )
    assert created["tasks"][0]["due_date"] == TODAY
    assert submitted["tasks"][0]["productivity_pct"] is None
