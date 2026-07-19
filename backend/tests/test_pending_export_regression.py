"""Pending Benchmark export — regression invariants vs the pre-day-part logic.

The export used to source its numeric rows verbatim from
get_daily_benchmark_ledger (one merged row per employee + date + sub-activity,
live master values). It now reads get_period_benchmark_ledger (one row per
period, frozen snapshots). For an unedited Activity Master the two MUST agree
on every aggregate: same employees, same dates, same per-employee and
per-sub-activity target/actual/pending totals — splitting a date into periods
may only add rows, never quantity. The old ledger still powers the live
alert/performance views, so this is also a live-view <-> export consistency
pin, not just a migration artifact.
"""
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.modules.activity_master.service import (
    get_cycle_task_activities,
    get_daily_benchmark_ledger,
)
from app.modules.benchmarks.service import get_pending_benchmark_export
from tests.test_pending_export_day_parts import (  # noqa: F401
    WORK,
    _create_submit,
    _make_numeric_sub,
    _make_task_sub,
    _submit_split,
    _task,
    day_parts_on,
    pm_header,
    setup_author,
)

TODAY = date.today()


@pytest.fixture()
def mixed_dataset(client, setup_author, pm_header, day_parts_on):
    """Two employees, five numeric sub-activities + one lumpsum, exercising:
    full day, both halves (same activity), single halves, legacy half-day,
    multiple activities in one half, over- and under-achievement."""
    e1 = setup_author(email="r1@x.com", code="R-1", proj_code="RP-1")
    e2 = setup_author(email="r2@x.com", code="R-2", proj_code="RP-2")

    _, full = _make_numeric_sub(client, pm_header, value=100, name="REG-FULL")
    _, both = _make_numeric_sub(client, pm_header, value=120, name="REG-BOTH", count_field="bom")
    _, am = _make_numeric_sub(client, pm_header, value=200, name="REG-AM", count_field="docs")
    _, pm_ = _make_numeric_sub(client, pm_header, value=80, name="REG-PM", count_field="spares")
    _, old = _make_numeric_sub(client, pm_header, value=90, name="REG-OLD", count_field="records")
    _, lump = _make_task_sub(client, pm_header, name="REG-TASK", period=1)

    cycle_start = TODAY - timedelta(days=(TODAY.weekday() - 4) % 7)
    d = {i: max(cycle_start, TODAY - timedelta(days=i)) for i in range(3)}

    _create_submit(client, e1["header"], {
        "report_date": d[0].isoformat(), "day_status": "work_at_office",
        "location": "chennai", "remarks": "e1 full day",
        "tasks": [
            _task(e1["project"].id, full["id"], tags_count=85),
            _task(e1["project"].id, lump["id"]),
        ],
    })
    if d[1] != d[0]:
        _submit_split(
            client, e1["header"],
            {**WORK, "remarks": "e1 am",
             "tasks": [
                 _task(e1["project"].id, both["id"], bom_count=40),
                 _task(e1["project"].id, am["id"], docs_count=90),
             ]},
            {**WORK, "remarks": "e1 pm",
             "tasks": [_task(e1["project"].id, both["id"], bom_count=70)]},
            report_date=d[1],
        )
    _submit_split(
        client, e2["header"],
        {"period_status": "leave", "remarks": "e2 am leave"},
        {**WORK, "remarks": "e2 pm",
         "tasks": [_task(e2["project"].id, pm_["id"], spares_count=55)]},
        report_date=d[0],
    )
    if d[2] != d[1]:
        _create_submit(client, e2["header"], {
            "report_date": d[2].isoformat(), "day_status": "half_day",
            "location": "chennai", "remarks": "e2 old half",
            "tasks": [_task(e2["project"].id, old["id"], records_count=30)],
        })
    return {"e1": e1, "e2": e2}


def _old_rows(db):
    """The numeric row source EXACTLY as the pre-change export consumed it."""
    return get_daily_benchmark_ledger(db, employee_ids=None, today=TODAY)


def _new(db):
    return get_pending_benchmark_export(db, cycle=0, today=TODAY)


def _numeric(rows):
    return [r for r in rows if not isinstance(r["target"], str)]


def test_employees_and_dates_match_old_row_source(db, mixed_dataset):
    old = _old_rows(db)
    new = _numeric(_new(db)["rows"])
    old_emps = {(r["employee_id"], r["date"]) for r in old}
    # New rows key by label; map back through the seeded employees.
    codes = {mixed_dataset[k]["emp"].employee_code for k in ("e1", "e2")}
    assert {lbl.split(" - ")[0] for r in new for lbl in [r["employee_label"]]} == codes
    assert {r["date"] for r in new} == {d for (_e, d) in old_emps}


def test_per_sub_activity_totals_match_old_row_source(db, mixed_dataset):
    old, new = _old_rows(db), _numeric(_new(db)["rows"])

    def agg(rows, key, tkey="target", akey="actual"):
        out = {}
        for r in rows:
            t, a = out.setdefault(key(r), [Decimal("0"), Decimal("0")])
            out[key(r)] = [t + Decimal(str(r[tkey])), a + Decimal(str(r[akey]))]
        return out

    old_by_sub = agg(old, lambda r: r["sub_activity_name"])
    new_by_sub = agg(new, lambda r: r["sub_activity"])
    assert old_by_sub == new_by_sub
    # Net cycle pending per sub-activity (the TOTAL-row rule) also agrees.
    for sub, (t, a) in old_by_sub.items():
        nt, na = new_by_sub[sub]
        assert max(Decimal("0"), t - a) == max(Decimal("0"), nt - na), sub


def test_per_employee_totals_match_old_row_source(db, mixed_dataset):
    old, new = _old_rows(db), _numeric(_new(db)["rows"])
    old_t = Counter()
    old_a = Counter()
    for r in old:
        old_t[r["employee_id"]] += Decimal(str(r["target"]))
        old_a[r["employee_id"]] += Decimal(str(r["actual"]))
    label_of = {
        f"{mixed_dataset[k]['emp'].employee_code} - {mixed_dataset[k]['emp'].full_name}":
        mixed_dataset[k]["emp"].id
        for k in ("e1", "e2")
    }
    new_t = Counter()
    new_a = Counter()
    for r in new:
        new_t[label_of[r["employee_label"]]] += Decimal(str(r["target"]))
        new_a[label_of[r["employee_label"]]] += Decimal(str(r["actual"]))
    assert old_t == new_t
    assert old_a == new_a


def test_row_count_grows_only_by_period_splits(db, mixed_dataset):
    """Detail rows may only exceed the old count where one date genuinely has
    two periods of one sub-activity; nothing disappears, nothing duplicates."""
    old, new = _old_rows(db), _numeric(_new(db)["rows"])
    old_keys = Counter((r["employee_id"], r["date"], r["sub_activity_id"]) for r in old)
    new_keys = Counter(
        (r["date"], r["sub_activity_id"], r["day_part"]) for r in new
    )
    assert set(old_keys.values()) == {1}
    assert set(new_keys.values()) == {1}          # no duplicate (date, sub, part)
    # Same (date, sub) universe: every old row maps to >= 1 new period row.
    assert {(d, s) for (_e, d, s) in old_keys} == {(d, s) for (d, s, _p) in new_keys}


def test_task_based_rows_match_old_source_exactly(db, mixed_dataset):
    old_tasks = get_cycle_task_activities(db, employee_ids=None, today=TODAY)
    new_tasks = [r for r in _new(db)["rows"] if isinstance(r["target"], str)]
    assert len(new_tasks) == len(old_tasks) == 1
    (nt,), (ot,) = new_tasks, old_tasks
    # Status/deadline text derived from the same fields — unchanged by Day Part.
    assert ot["is_completed"] is False
    assert nt["target"] == "FINISH WITHIN A DAY"
    assert nt["date"] == ot["report_date"]
    assert nt["day_part"] == "FULL DAY"


def test_cycle_dates_and_day_part_labels(db, mixed_dataset):
    data = _new(db)
    assert data["cycle_start"].weekday() == 4 and data["cycle_end"].weekday() == 3
    allowed = {"FULL DAY", "FIRST HALF", "SECOND HALF", "HALF DAY (LEGACY)"}
    assert {r["day_part"] for r in data["rows"]} <= allowed
