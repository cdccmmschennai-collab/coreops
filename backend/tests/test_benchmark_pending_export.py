"""Pending Benchmark XLSX export (GET /benchmarks/pending-export.xlsx) and the
Fri..Thu cycle bounds behind it. The export reuses the frozen daily ledger +
reconciled pending; these tests cover the cycle math, the previous/current
cycle selection, the reconciled-pending filter, and the grouped-header layout
with per-employee TOTAL rows."""
from datetime import date, datetime, timedelta
from io import BytesIO

import openpyxl
import pytest

from app.modules.activity_master.service import compute_week_bounds
from app.modules.projects.models import ProjectStatus
from app.modules.reports_export.export import date_range_label
from app.modules.users.models import UserRole

BASE = "/api/v1/work-reports"
EXPORT_URL = "/api/v1/benchmarks/pending-export.xlsx"
TODAY_D = date.today()


@pytest.fixture()
def setup_author(make_user, make_employee, make_project, make_project_member, login):
    def _make(*, email="emp@x.com", code="E-1", proj_code="P-1", first_name="Test", last_name="User"):
        u = make_user(email, role=UserRole.employee)
        e = make_employee(employee_code=code, user_id=u.id, first_name=first_name, last_name=last_name)
        p = make_project(code=proj_code, status=ProjectStatus.active)
        make_project_member(project_id=p.id, employee_id=e.id)
        return {"user": u, "emp": e, "project": p, "header": login(email)}

    return _make


@pytest.fixture()
def activity_admin(auth_header):
    return auth_header(email="pm@x.com", role=UserRole.project_manager)


def _make_sub_activity(client, admin_header, *, benchmark_value, name="Sub", count_field="tags"):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity for {name}"}, headers=admin_header
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={
            "name": name, "benchmark_type": "NUMERIC",
            "benchmark_value": benchmark_value, "relevant_count_field": count_field,
        },
        headers=admin_header,
    ).json()
    return a, sub


def _make_task_sub(client, admin_header, *, name):
    """TASK_BASED (lumpsum) sub-activity with a 1-day completion period."""
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity for {name}"}, headers=admin_header
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={"name": name, "benchmark_type": "TASK_BASED"},
        headers=admin_header,
    ).json()
    client.patch(
        f"/api/v1/activity-master/sub-activities/{sub['id']}",
        json={"benchmark_period_days": 1},
        headers=admin_header,
    )
    return a, sub


def _submit(client, header, project_id, sub_id, report_date, qty, count_field="tags"):
    payload = {
        "report_date": report_date.isoformat(),
        "tasks": [{
            "project_id": str(project_id), "description": "work",
            "sub_activity_id": sub_id, f"{count_field}_count": qty,
        }],
    }
    created = client.post(BASE, headers=header, json=payload)
    assert created.status_code == 201, created.text
    res = client.post(f"{BASE}/{created.json()['id']}/submit", headers=header)
    assert res.status_code == 200, res.text


def _prev_cycle() -> tuple[date, date]:
    start, end = compute_week_bounds(TODAY_D)
    return start - timedelta(days=7), end - timedelta(days=7)


def _cell_date(value):
    return value.date() if isinstance(value, datetime) else value


def _load_sheet(content: bytes):
    return openpyxl.load_workbook(BytesIO(content)).active


def _fill(cell):
    """The cell's solid fill RGB, or None when unfilled."""
    return cell.fill.fgColor.rgb if cell.fill and cell.fill.fill_type else None


def _total_rows_by_label(ws):
    """Map each employee label -> its TOTAL row index. The TOTAL row now repeats
    the employee's EMP CODE & NAME in column 1 (so a per-employee Excel filter
    keeps it), so read it directly."""
    return {
        ws.cell(r, 1).value: r
        for r in range(3, ws.max_row + 1)
        if ws.cell(r, 5).value == "TOTAL"
    }


def _find_row(ws, label, sub, on_date):
    """Row index of a specific employee/sub-activity/date detail row."""
    for r in range(3, ws.max_row + 1):
        if (
            ws.cell(r, 1).value == label
            and ws.cell(r, 5).value == sub
            and _cell_date(ws.cell(r, 2).value) == on_date
        ):
            return r
    raise AssertionError(f"row not found: {label} / {sub} / {on_date}")


# Soft grading tints applied to employee TOTAL rows (see export._grade_fill).
GREEN = "FFC6EFCE"
RED = "FFFFC7CE"

# Column map after the per-group TOTAL sub-columns + ACHIEVEMENT % were added.
TGT_TAGS, TGT_DOCS, TGT_TOTAL = 6, 7, 10
ACT_TAGS, ACT_DOCS, ACT_TOTAL = 11, 12, 15
PEN_TAGS, PEN_DOCS, PEN_TOTAL = 16, 17, 20
ACH, CYC_START, CYC_END = 21, 22, 23


# --- cycle bounds -----------------------------------------------------------

def test_week_bounds_are_friday_to_thursday():
    friday = date(2026, 7, 3)  # a Friday
    thursday = date(2026, 7, 9)
    # Every day of the cycle, Fri through Thu, maps to the same bounds.
    for offset in range(7):
        assert compute_week_bounds(friday + timedelta(days=offset)) == (friday, thursday)
    # The next Friday starts a fresh cycle.
    assert compute_week_bounds(date(2026, 7, 10)) == (date(2026, 7, 10), date(2026, 7, 16))


# --- endpoint guards --------------------------------------------------------

def test_export_requires_project_manager(client, setup_author):
    a = setup_author()
    assert client.get(EXPORT_URL, headers=a["header"]).status_code == 403


def test_export_rejects_unknown_cycle(client, activity_admin):
    assert client.get(f"{EXPORT_URL}?cycle=nope", headers=activity_admin).status_code == 422


# --- export content ---------------------------------------------------------

def test_default_export_is_previous_cycle_with_grouped_header_and_total(
    client, setup_author, activity_admin,
):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, cycle_end = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 200)  # pending 50
    # A current-cycle shortfall must NOT leak into the default (previous) export.
    _submit(client, a["header"], a["project"].id, sub["id"], TODAY_D, 10)

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200
    assert res.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert f"BENCHMARK REPORT {date_range_label(cycle_start, cycle_end)}.xlsx" in (
        res.headers["content-disposition"]
    )

    ws = _load_sheet(res.content)
    # Grouped header: row 1 = merged group labels only; row 2 = the real
    # (filterable) header row with an UPPERCASE label in every column.
    assert [ws.cell(2, c).value for c in range(1, 6)] == [
        "EMP CODE & NAME", "DATE", "PROJECT CODE & TITLE", "ACTIVITY", "SUB ACTIVITY",
    ]
    assert ws.cell(1, TGT_TAGS).value == "BENCHMARK TARGET"
    assert ws.cell(1, ACT_TAGS).value == "ACTUAL COMPLETED"
    assert ws.cell(1, PEN_TAGS).value == "PENDING BENCHMARK"
    assert ws.cell(2, ACH).value == "ACHIEVEMENT %"
    assert ws.cell(2, CYC_START).value == "CYCLE START"
    assert ws.cell(2, CYC_END).value == "CYCLE END"
    # Each group: four unit columns then a per-group TOTAL column.
    for start in (TGT_TAGS, ACT_TAGS, PEN_TAGS):
        assert [ws.cell(2, start + i).value for i in range(5)] == [
            "TAGS", "DOCS", "BOM", "SPARES", "TOTAL",
        ]
    merges = {str(r) for r in ws.merged_cells.ranges}
    # Group label spans the four unit cols only; the TOTAL col sits outside it.
    assert {"F1:I1", "K1:N1", "P1:S1"} <= merges
    # No vertical merges: row 2 must stay a clean AutoFilter row (a merged
    # A1:A2 leaves A2 an empty MergedCell and breaks per-column filtering).
    assert "A1:A2" not in merges and "W1:W2" not in merges
    assert ws.auto_filter.ref == "A2:W4"

    # One data row (previous cycle only) then the employee TOTAL row.
    assert ws.cell(3, 1).value == "E-1 - Test User"
    assert _cell_date(ws.cell(3, 2).value) == cycle_start
    assert ws.cell(3, 3).value == "P-1 - Test Project"
    assert ws.cell(3, 5).value == "FMTL"
    assert ws.cell(3, TGT_TAGS).value == 250        # target -> Tags
    assert ws.cell(3, TGT_TAGS + 1).value is None   # Docs stays blank
    assert ws.cell(3, ACT_TAGS).value == 200        # actual -> Tags
    assert ws.cell(3, PEN_TAGS).value == 50         # pending -> Tags
    assert ws.cell(3, ACH).value is None            # % only on the TOTAL row
    assert _cell_date(ws.cell(3, CYC_START).value) == cycle_start
    assert _cell_date(ws.cell(3, CYC_END).value) == cycle_end

    # TOTAL row repeats the full "CODE - NAME" so an employee filter keeps it.
    assert ws.cell(4, 1).value == "E-1 - Test User"
    assert ws.cell(4, 5).value == "TOTAL"
    assert ws.cell(4, TGT_TAGS).value == 250
    assert ws.cell(4, TGT_TOTAL).value == 250       # cross-unit group total
    assert ws.cell(4, ACT_TAGS).value == 200
    assert ws.cell(4, ACT_TOTAL).value == 200
    assert ws.cell(4, PEN_TAGS).value == 50
    assert ws.cell(4, PEN_TOTAL).value == 50
    # Full cycle 200/250 = 80% -> below 95, whole TOTAL row filled light red.
    assert ws.cell(4, ACH).value == 0.8
    assert ws.cell(4, ACH).number_format == "0%"
    assert _fill(ws.cell(4, 1)) == RED
    assert _fill(ws.cell(4, ACH)) == RED
    # Detail rows are never graded.
    assert _fill(ws.cell(3, 1)) is None
    assert ws.max_row == 4  # nothing from the current cycle


def test_cycle_current_exports_the_active_cycle(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=120, name="FMTL")
    _submit(client, a["header"], a["project"].id, sub["id"], TODAY_D, 100)  # pending 20

    res = client.get(f"{EXPORT_URL}?cycle=current", headers=activity_admin)
    assert res.status_code == 200
    ws = _load_sheet(res.content)
    assert ws.cell(3, 1).value == "E-1 - Test User"
    assert _cell_date(ws.cell(3, 2).value) == TODAY_D
    assert ws.cell(3, PEN_TAGS).value == 20
    assert ws.cell(4, 5).value == "TOTAL"
    # Full cycle 100/120 = 83% (rounded) -> below 95, TOTAL row light red.
    assert ws.cell(4, ACH).value == 0.83
    assert _fill(ws.cell(4, 1)) == RED


def test_employees_performance_cycle_param_switches_window(
    client, setup_author, activity_admin,
):
    """The comparison table defaults to the current cycle but can review the
    previous one — a shortfall reported last cycle shows zeros by default and
    its real numbers under ?cycle=previous."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 200)  # pending 50

    def rows(query: str = "") -> dict:
        res = client.get(f"/api/v1/benchmarks/employees-performance{query}", headers=activity_admin)
        assert res.status_code == 200
        return {r["employee_code"]: r for r in res.json()["items"]}

    current = rows()  # default = current cycle: roster row present, zeros
    assert float(current["E-1"]["pending"]) == 0
    assert float(current["E-1"]["target"]) == 0

    prev = rows("?cycle=previous")
    assert float(prev["E-1"]["pending"]) == 50
    assert float(prev["E-1"]["target"]) == 250
    assert float(prev["E-1"]["actual"]) == 200

    assert client.get(
        "/api/v1/benchmarks/employees-performance?cycle=nope", headers=activity_admin
    ).status_code == 422


def test_task_based_lumpsum_rows_case_a_and_b(client, db, setup_author, activity_admin):
    """Overdue TASK_BASED rows join the export. CASE A (count-based lumpsum,
    benchmark_value + counted unit) renders "1000 TAGS PER DAY" / "500 TAGS" /
    "500 TAGS" and contributes its bare numbers to the TOTAL row; CASE B
    (plain finish-by-due task) renders "FINISH WITHIN A DAY" /
    "NOT COMPLETED" / "N DAYS OVERDUE" and contributes nothing to totals.
    The employee here has NO numeric pending — task rows alone must include
    them in the export."""
    import uuid as uuid_mod

    from app.modules.activity_master.models import ActivityMaster
    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, sub_a = _make_task_sub(client, activity_admin, name="LUMPSUM-A")
    _, sub_b = _make_task_sub(client, activity_admin, name="LUMPSUM-B")
    # CASE A: give LUMPSUM-A a count-based lumpsum benchmark (1000 tags).
    master_a = db.get(ActivityMaster, uuid_mod.UUID(sub_a["id"]))
    master_a.benchmark_value = 1000
    master_a.relevant_count_field = "tags"
    db.commit()

    cycle_start, cycle_end = _prev_cycle()
    payload = {
        "report_date": cycle_start.isoformat(),
        "tasks": [
            {
                "project_id": str(a["project"].id), "description": "lumpsum work",
                "sub_activity_id": sub_a["id"], "tags_count": 500,
            },
            {
                "project_id": str(a["project"].id), "description": "task work",
                "sub_activity_id": sub_b["id"],
            },
        ],
    }
    created = client.post(BASE, headers=a["header"], json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=a["header"]).status_code == 200

    # Anchor both due dates inside the previous cycle: overdue is evaluated as
    # of the cycle's end. B lands 3 days before cycle end -> "3 DAYS OVERDUE".
    due_by_sub = {sub_a["id"]: cycle_end - timedelta(days=5), sub_b["id"]: cycle_end - timedelta(days=3)}
    for t in body["tasks"]:
        row = db.get(WorkReportTask, uuid_mod.UUID(t["id"]))
        row.due_date = due_by_sub[str(row.sub_activity_id)]
    db.commit()

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200
    ws = _load_sheet(res.content)

    # Rows sort by sub-activity name within the date: LUMPSUM-A then LUMPSUM-B.
    assert ws.cell(3, 5).value == "LUMPSUM-A"
    assert ws.cell(3, TGT_TAGS).value == "1000 TAGS PER DAY"   # target -> TAGS
    assert ws.cell(3, ACT_TAGS).value == "500 TAGS"           # actual -> TAGS
    assert ws.cell(3, PEN_TAGS).value == "500 TAGS"           # pending -> TAGS

    assert ws.cell(4, 5).value == "LUMPSUM-B"
    assert ws.cell(4, TGT_TAGS).value == "FINISH WITHIN A DAY"
    assert ws.cell(4, ACT_TAGS).value == "NOT COMPLETED"
    assert ws.cell(4, PEN_TAGS).value == "3 DAYS OVERDUE"

    # TOTAL: only CASE A's bare numbers count — no text pollution.
    assert ws.cell(5, 5).value == "TOTAL"
    assert ws.cell(5, TGT_TAGS).value == 1000
    assert ws.cell(5, ACT_TAGS).value == 500
    assert ws.cell(5, PEN_TAGS).value == 500
    # ACHIEVEMENT %: count-based lumpsum participates (500/1000 = 50%), the
    # non-count CASE B text row contributes nothing and doesn't break the math.
    assert ws.cell(5, ACH).value == 0.5
    assert _fill(ws.cell(5, 1)) == RED


def test_later_overachievement_offsets_earlier_shortage(
    client, setup_author, activity_admin,
):
    """A later day's surplus offsets an earlier day's shortfall at the cycle
    TOTAL, even though each detail row keeps its own daily shortage. The
    employee (fully recovered, nothing net pending) is STILL exported — the
    full-cycle report is not filtered on pending > 0."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    monday = cycle_start + timedelta(days=3)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 100)  # short 150
    _submit(client, a["header"], a["project"].id, sub["id"], monday, 400)       # surplus 150

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200
    ws = _load_sheet(res.content)
    label = "E-1 - Test User"

    # Both days appear, each with its OWN daily shortage.
    early = _find_row(ws, label, "FMTL", cycle_start)
    assert ws.cell(early, PEN_TAGS).value == 150   # early day still shows 150
    late = _find_row(ws, label, "FMTL", monday)
    assert ws.cell(late, PEN_TAGS).value == 0      # over-target day shows 0

    # TOTAL nets the whole cycle: 500 target / 500 actual -> 0 pending, 100%.
    total = _total_rows_by_label(ws)[label]
    assert ws.cell(total, TGT_TAGS).value == 500
    assert ws.cell(total, ACT_TAGS).value == 500
    assert ws.cell(total, PEN_TAGS).value == 0     # NOT 150 (sum of daily shortages)
    assert ws.cell(total, PEN_TOTAL).value == 0
    assert ws.cell(total, ACH).value == 1.0
    assert _fill(ws.cell(total, 1)) == GREEN


def test_earlier_overachievement_offsets_later_shortage(
    client, setup_author, activity_admin,
):
    """The mirror case: an early day's surplus offsets a later day's shortfall
    at the cycle TOTAL. The later short day keeps its own daily shortage, but
    the netted TOTAL pending is 0."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    monday = cycle_start + timedelta(days=3)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 400)  # surplus 150
    _submit(client, a["header"], a["project"].id, sub["id"], monday, 100)       # short 150

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"

    assert ws.cell(_find_row(ws, label, "FMTL", cycle_start), PEN_TAGS).value == 0
    assert ws.cell(_find_row(ws, label, "FMTL", monday), PEN_TAGS).value == 150

    total = _total_rows_by_label(ws)[label]
    assert ws.cell(total, PEN_TAGS).value == 0     # 500 target / 500 actual
    assert ws.cell(total, ACH).value == 1.0
    assert _fill(ws.cell(total, 1)) == GREEN


def test_achievement_grades_full_cycle_not_visible_pending(
    client, setup_author, activity_admin,
):
    """ACHIEVEMENT % and the TOTAL-row colour come from the employee's WHOLE
    Fri..Thu cycle, not the pending rows shown in the sheet. An overachiever
    with one lagging day still reads green; 95-99% is left unfilled; <95% is
    red (covered by the default-export test)."""
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    day1, day2 = cycle_start, cycle_start + timedelta(days=1)

    # GREEN: an early day's surplus is never carried forward, so day2's deficit
    # keeps a visible pending row — yet the full cycle is 250/200 = 125%.
    green = setup_author(email="g@x.com", code="G-1", proj_code="PG", last_name="Green")
    _submit(client, green["header"], green["project"].id, sub["id"], day1, 160)
    _submit(client, green["header"], green["project"].id, sub["id"], day2, 90)

    # NO FILL: full cycle 194/200 = 97%, the acceptable band -> no grade fill.
    acc = setup_author(email="a@x.com", code="A-1", proj_code="PA", last_name="Acceptable")
    _submit(client, acc["header"], acc["project"].id, sub["id"], day1, 94)
    _submit(client, acc["header"], acc["project"].id, sub["id"], day2, 100)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    rows = _total_rows_by_label(ws)

    g = rows["G-1 - Test Green"]
    assert ws.cell(g, ACH).value == 1.25
    assert _fill(ws.cell(g, 1)) == GREEN
    assert _fill(ws.cell(g, ACH)) == GREEN
    # The over-target day that explains the >100% score is now visible too,
    # reading pending 0 (previously it was hidden).
    over = _find_row(ws, "G-1 - Test Green", "FMTL", day1)
    assert ws.cell(over, ACT_TAGS).value == 160
    assert ws.cell(over, PEN_TAGS).value == 0

    a = rows["A-1 - Test Acceptable"]
    assert ws.cell(a, ACH).value == 0.97
    assert _fill(ws.cell(a, 1)) is None
    assert _fill(ws.cell(a, ACH)) is None


def test_included_employee_shows_full_cycle_rows(client, db, setup_author, activity_admin):
    """Once an employee is included (one lagging numeric day), the export shows
    their WHOLE cycle so the % is legible: the over-target day (pending 0) and
    a lumpsum they finished this cycle appear alongside the shortfall row. The
    completed non-count task contributes nothing to the numeric %."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, num = _make_sub_activity(client, activity_admin, benchmark_value=100, name="NUM")
    _, done = _make_task_sub(client, activity_admin, name="DONE")
    cycle_start, _ = _prev_cycle()
    day1, day2, day3 = cycle_start, cycle_start + timedelta(days=1), cycle_start + timedelta(days=2)

    _submit(client, a["header"], a["project"].id, num["id"], day1, 200)  # over target
    _submit(client, a["header"], a["project"].id, num["id"], day2, 80)   # short 20 -> included

    payload = {
        "report_date": day3.isoformat(),
        "tasks": [{"project_id": str(a["project"].id), "description": "x", "sub_activity_id": done["id"]}],
    }
    body = client.post(BASE, headers=a["header"], json=payload).json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=a["header"]).status_code == 200
    task = db.get(WorkReportTask, uuid_mod.UUID(body["tasks"][0]["id"]))
    task.due_date, task.is_completed, task.completed_date = day3, True, day3
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"

    # Over-target day is visible with pending 0 (would have been hidden before).
    over = _find_row(ws, label, "NUM", day1)
    assert ws.cell(over, TGT_TAGS).value == 100
    assert ws.cell(over, ACT_TAGS).value == 200
    assert ws.cell(over, PEN_TAGS).value == 0
    # The lagging day.
    assert ws.cell(_find_row(ws, label, "NUM", day2), PEN_TAGS).value == 20
    # Completed non-count lumpsum: FINISH WITHIN A DAY / FINISHED / NO PENDING.
    d = _find_row(ws, label, "DONE", day3)
    assert ws.cell(d, TGT_TAGS).value == "FINISH WITHIN A DAY"
    assert ws.cell(d, ACT_TAGS).value == "FINISHED"
    assert ws.cell(d, PEN_TAGS).value == "NO PENDING"

    # % is numeric-only: (200 + 80) / (100 + 100) = 140%; the FINISHED task
    # doesn't move it. The visible rows now explain the >100% score.
    total = _total_rows_by_label(ws)[label]
    assert ws.cell(total, ACH).value == 1.4
    assert _fill(ws.cell(total, 1)) == GREEN


def test_completed_count_based_lumpsum_counts_toward_percentage(
    client, db, setup_author, activity_admin,
):
    """A count-based lumpsum finished this cycle renders numbers + NO PENDING
    and its numeric target/actual join the Achievement %."""
    import uuid as uuid_mod

    from app.modules.activity_master.models import ActivityMaster
    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, num = _make_sub_activity(client, activity_admin, benchmark_value=100, name="NUM")
    _, lump = _make_task_sub(client, activity_admin, name="LUMP")
    master = db.get(ActivityMaster, uuid_mod.UUID(lump["id"]))
    master.benchmark_value, master.relevant_count_field = 1000, "tags"
    db.commit()

    cycle_start, _ = _prev_cycle()
    day1, day2 = cycle_start, cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, num["id"], day1, 40)  # 40/100 -> included

    payload = {
        "report_date": day2.isoformat(),
        "tasks": [{
            "project_id": str(a["project"].id), "description": "x",
            "sub_activity_id": lump["id"], "tags_count": 1000,
        }],
    }
    body = client.post(BASE, headers=a["header"], json=payload).json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=a["header"]).status_code == 200
    task = db.get(WorkReportTask, uuid_mod.UUID(body["tasks"][0]["id"]))
    task.due_date, task.is_completed, task.completed_date = day2, True, day2
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"

    rl = _find_row(ws, label, "LUMP", day2)
    assert ws.cell(rl, TGT_TAGS).value == "1000 TAGS PER DAY"
    assert ws.cell(rl, ACT_TAGS).value == "1000 TAGS"
    assert ws.cell(rl, PEN_TAGS).value == "NO PENDING"

    # (40 + 1000) / (100 + 1000) = 1040/1100 = 95% (acceptable band, no fill).
    total = _total_rows_by_label(ws)[label]
    assert ws.cell(total, ACH).value == 0.95
    assert _fill(ws.cell(total, 1)) is None


# --- full-cycle export: achievers included, cycle-netted totals -------------

def test_employee_with_no_pending_is_still_exported(client, setup_author, activity_admin):
    """An employee who met every benchmark exactly (nothing pending) is still
    exported — the full-cycle report is not filtered on pending > 0."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 100)  # exactly met

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    assert label in _total_rows_by_label(ws)
    total = _total_rows_by_label(ws)[label]
    assert ws.cell(total, PEN_TAGS).value == 0
    assert ws.cell(total, ACH).value == 1.0
    assert _fill(ws.cell(total, 1)) == GREEN


def test_employee_exceeding_100_percent_is_exported(client, setup_author, activity_admin):
    """An overachiever (actual > target, zero pending) is exported and their
    ACHIEVEMENT % is NOT capped at 100."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 175)  # 175%

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _total_rows_by_label(ws)["E-1 - Test User"]
    assert ws.cell(total, PEN_TAGS).value == 0
    assert ws.cell(total, ACH).value == 1.75  # uncapped
    assert _fill(ws.cell(total, 1)) == GREEN


def test_total_row_repeats_exact_employee_code_and_name(client, setup_author, activity_admin):
    """The TOTAL row's EMP CODE & NAME cell holds the IDENTICAL value used on
    the detail rows (not blank, not the bare name) so an Excel employee filter
    returns both the detail rows and the TOTAL row."""
    a = setup_author(code="CDC002", first_name="RAMASRINIVASAMOORTHY", last_name="D")
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    expected = "CDC002 - RAMASRINIVASAMOORTHY D"
    detail = _find_row(ws, expected, "FMTL", cycle_start)
    total = _total_rows_by_label(ws)[expected]
    assert ws.cell(detail, 1).value == expected
    # TOTAL cell equals the detail cell exactly — same string, same case/spacing.
    assert ws.cell(total, 1).value == ws.cell(detail, 1).value == expected


def test_percentage_uses_the_entire_cycle(client, setup_author, activity_admin):
    """ACHIEVEMENT % is computed from the whole cycle's summed actual/target,
    not from any single visible row: (120 + 60) / (100 + 100) = 90%."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 120)  # over
    _submit(client, a["header"], a["project"].id, sub["id"], day2, 60)          # short

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _total_rows_by_label(ws)["E-1 - Test User"]
    # Cross-day: totals net to 180/200 = 90%, pending = max(0, 200-180) = 20.
    assert ws.cell(total, TGT_TAGS).value == 200
    assert ws.cell(total, ACT_TAGS).value == 180
    assert ws.cell(total, PEN_TAGS).value == 20
    assert ws.cell(total, ACH).value == 0.9


def test_no_numeric_target_does_not_divide_by_zero(client, db, setup_author, activity_admin):
    """An employee whose only benchmark activity is a plain (non-count)
    TASK_BASED task has no numeric target — the export includes them without a
    division-by-zero, leaving ACHIEVEMENT % blank."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, task = _make_task_sub(client, activity_admin, name="PLAIN")
    cycle_start, cycle_end = _prev_cycle()
    payload = {
        "report_date": cycle_start.isoformat(),
        "tasks": [{"project_id": str(a["project"].id), "description": "x", "sub_activity_id": task["id"]}],
    }
    body = client.post(BASE, headers=a["header"], json=payload).json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=a["header"]).status_code == 200
    row = db.get(WorkReportTask, uuid_mod.UUID(body["tasks"][0]["id"]))
    row.due_date = cycle_end - timedelta(days=1)
    db.commit()

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200  # no ZeroDivisionError
    ws = _load_sheet(res.content)
    total = _total_rows_by_label(ws)["E-1 - Test User"]
    assert ws.cell(total, ACH).value is None  # no numeric target -> blank
    assert _fill(ws.cell(total, 1)) is None


def test_compensation_is_scoped_per_employee(client, setup_author, activity_admin):
    """One employee's overachievement must NOT offset a different employee's
    shortfall. Each employee's TOTAL nets only their own cycle."""
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()

    over = setup_author(email="o@x.com", code="O-1", proj_code="PO", last_name="Over")
    _submit(client, over["header"], over["project"].id, sub["id"], cycle_start, 300)  # +200

    under = setup_author(email="u@x.com", code="U-1", proj_code="PU", last_name="Under")
    _submit(client, under["header"], under["project"].id, sub["id"], cycle_start, 40)  # short 60

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    totals = _total_rows_by_label(ws)

    u = totals["U-1 - Test Under"]
    assert ws.cell(u, PEN_TAGS).value == 60   # NOT wiped out by O-1's surplus
    assert ws.cell(u, ACH).value == 0.4
    o = totals["O-1 - Test Over"]
    assert ws.cell(o, PEN_TAGS).value == 0
    assert ws.cell(o, ACH).value == 3.0


def test_compensation_is_scoped_per_benchmark_unit(client, setup_author, activity_admin):
    """Within one employee, a TAGS surplus must NOT offset a DOCS shortfall —
    pending is netted per unit. TAGS 150/100 (over) and DOCS 40/100 (short 60)
    leaves DOCS pending 60, TAGS pending 0."""
    a = setup_author()
    _, tags_sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="TAGGED")
    _, docs_sub = _make_sub_activity(
        client, activity_admin, benchmark_value=100, name="DOCD", count_field="docs"
    )
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)  # one work report per date, so split days
    _submit(client, a["header"], a["project"].id, tags_sub["id"], cycle_start, 150)  # +50 tags
    _submit(client, a["header"], a["project"].id, docs_sub["id"], day2, 40, count_field="docs")

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _total_rows_by_label(ws)["E-1 - Test User"]
    assert ws.cell(total, PEN_TAGS).value == 0    # tags fully met
    assert ws.cell(total, PEN_DOCS).value == 60   # docs shortfall NOT offset by tags surplus
    # % is still whole-cycle across units: (150 + 40) / (100 + 100) = 95%.
    assert ws.cell(total, ACH).value == 0.95
