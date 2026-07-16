"""Full-cycle Benchmark XLSX export (GET /benchmarks/pending-export.xlsx) and
the Fri..Thu cycle bounds behind it.

Layout and styling are matched cell-for-cell to the company reference workbook
(BENCHMARK REPORT 03 JUL - 09 JUL): 21 columns A..U, a two-level yellow header,
white body rows, bold white TOTAL rows, and a red/green shade on the
DIFFERENCE % cell ONLY. Each NUMERIC sub-activity gets its own TOTAL row
(per-unit target/actual/net-pending + its own uncapped achievement % and the
absolute difference from 100%). A purely TEXTUAL task sub-activity shows detail
rows only — no total, no percentages, no shading. Compensation is scoped to one
employee + cycle + sub-activity + unit and never crosses those bounds."""
from datetime import date, datetime, timedelta
from io import BytesIO

import openpyxl
import pytest

from app.modules.activity_master.service import compute_week_bounds
from app.modules.projects.models import ProjectStatus
from app.modules.reports_export.export import (
    _BORDER,
    _DATA_FONT,
    _PB_HEADER_FILL,
    _PB_HEADER_FONT,
    _PB_TOTAL_FONT,
    PENDING_SHEET_NAME,
    date_range_label,
)
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


def _make_task_sub(client, admin_header, *, name, period=1):
    """TASK_BASED (lumpsum) sub-activity with a `period`-day completion window."""
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
        json={"benchmark_period_days": period},
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


def _submit_task(client, header, project_id, sub_id, report_date):
    """Submit a plain task row (no counts) and return the created task id."""
    payload = {
        "report_date": report_date.isoformat(),
        "tasks": [{"project_id": str(project_id), "description": "x", "sub_activity_id": sub_id}],
    }
    body = client.post(BASE, headers=header, json=payload).json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=header).status_code == 200
    return body["tasks"][0]["id"]


def _prev_cycle() -> tuple[date, date]:
    start, end = compute_week_bounds(TODAY_D)
    return start - timedelta(days=7), end - timedelta(days=7)


def _cell_date(value):
    return value.date() if isinstance(value, datetime) else value


def _load_sheet(content: bytes):
    return openpyxl.load_workbook(BytesIO(content)).active


def _fill(cell):
    """The cell's solid fill RGB, or None when it has no visible fill."""
    return cell.fill.fgColor.rgb if cell.fill and cell.fill.fill_type else None


# --- column map (21 cols, A..U; ACHIEVEMENT % = F, DIFFERENCE % = G) ---------
EMP, DATE_C, PROJECT, ACTIVITY, SUB, ACH, DIFF = 1, 2, 3, 4, 5, 6, 7
TGT_TAGS, TGT_DOCS, TGT_BOM, TGT_SPARES = 8, 9, 10, 11
ACT_TAGS, ACT_DOCS, ACT_BOM, ACT_SPARES = 12, 13, 14, 15
PEN_TAGS, PEN_DOCS, PEN_BOM, PEN_SPARES = 16, 17, 18, 19
CYC_START, CYC_END = 20, 21
LAST_COL = 21

# The only two body colours, and they land on the DIFFERENCE % cell alone.
GREEN = "FFC6EFCE"   # achievement > 100%
RED = "FFFFC7CE"     # achievement < 95%
HEADER_YELLOW = "FFFFFF00"

# Exact widths from the reference workbook.
EXPECTED_WIDTHS = {
    "A": 26.0, "B": 12.0, "C": 86.0, "D": 22.0, "E": 118.140625,
    "F": 18.85546875, "G": 15.0,
    "H": 21.42578125, "I": 12.0, "J": 12.0, "K": 12.0,
    "L": 16.85546875, "M": 12.0, "N": 12.0, "O": 12.0,
    "P": 17.7109375, "Q": 12.0, "R": 12.0, "S": 12.0,
    "T": 13.0, "U": 13.0,
}
EXPECTED_MERGES = {"H1:K1", "L1:O1", "P1:S1"}


def _detail_row(ws, label, sub, on_date):
    """Row index of one employee/sub-activity/date DETAIL row (total rows carry
    no DATE, so they never match)."""
    for r in range(3, ws.max_row + 1):
        if (
            ws.cell(r, EMP).value == label
            and ws.cell(r, SUB).value == sub
            and _cell_date(ws.cell(r, DATE_C).value) == on_date
        ):
            return r
    raise AssertionError(f"detail row not found: {label} / {sub} / {on_date}")


def _sub_total_rows(ws, label, sub):
    """Every TOTAL row for an employee+sub-activity (a total row carries "TOTAL"
    in the PROJECT column)."""
    return [
        r for r in range(3, ws.max_row + 1)
        if ws.cell(r, EMP).value == label
        and ws.cell(r, SUB).value == sub
        and ws.cell(r, PROJECT).value == "TOTAL"
    ]


def _sub_total_row(ws, label, sub):
    rows = _sub_total_rows(ws, label, sub)
    assert rows, f"sub-activity total not found: {label} / {sub}"
    return rows[0]


def _all_total_rows(ws):
    """Every TOTAL row in the sheet, by PROJECT == 'TOTAL'."""
    return [r for r in range(3, ws.max_row + 1) if ws.cell(r, PROJECT).value == "TOTAL"]


def _assert_only_diff_cell_shaded(ws, row):
    """No cell on `row` carries a fill except (possibly) DIFFERENCE %."""
    shaded = [
        ws.cell(row, c).coordinate
        for c in range(1, LAST_COL + 1)
        if c != DIFF and _fill(ws.cell(row, c)) is not None
    ]
    assert shaded == [], f"row {row} must only ever shade its G cell; shaded: {shaded}"


# --- cycle bounds -----------------------------------------------------------

def test_week_bounds_are_friday_to_thursday():
    friday = date(2026, 7, 3)  # a Friday
    thursday = date(2026, 7, 9)
    for offset in range(7):
        assert compute_week_bounds(friday + timedelta(days=offset)) == (friday, thursday)
    assert compute_week_bounds(date(2026, 7, 10)) == (date(2026, 7, 10), date(2026, 7, 16))


# --- endpoint guards --------------------------------------------------------

def test_export_requires_project_manager(client, setup_author):
    a = setup_author()
    assert client.get(EXPORT_URL, headers=a["header"]).status_code == 403


def test_export_rejects_unknown_cycle(client, activity_admin):
    assert client.get(f"{EXPORT_URL}?cycle=nope", headers=activity_admin).status_code == 422


# --- layout: exact 21-column order, two-level header -------------------------

def test_default_export_is_previous_cycle_with_reference_layout(client, setup_author, activity_admin):
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
    assert ws.title == PENDING_SHEET_NAME

    # Row 2 = the real header row, in the exact required order A..U.
    assert [ws.cell(2, c).value for c in range(1, LAST_COL + 1)] == [
        "EMP CODE & NAME", "DATE", "PROJECT CODE & TITLE", "ACTIVITY", "SUB ACTIVITY",
        "ACHIEVEMENT %", "DIFFERENCE %",
        "TAGS", "DOCS", "BOM", "SPARES",
        "TAGS", "DOCS", "BOM", "SPARES",
        "TAGS", "DOCS", "BOM", "SPARES",
        "CYCLE START", "CYCLE END",
    ]
    # None of the withdrawn columns exist anywhere in the header.
    labels = {ws.cell(2, c).value for c in range(1, LAST_COL + 1)}
    assert labels.isdisjoint(
        {"ROW TYPE", "TARGET TOTAL", "ACTUAL TOTAL", "PENDING TOTAL", "EMPLOYEE TOTAL"}
    )
    # Row 1 holds ONLY the three merged group labels; A1:G1 and T1:U1 are blank.
    assert ws.cell(1, TGT_TAGS).value == "BENCHMARK TARGET"
    assert ws.cell(1, ACT_TAGS).value == "ACTUAL COMPLETED"
    assert ws.cell(1, PEN_TAGS).value == "PENDING BENCHMARK"
    for c in list(range(1, DIFF + 1)) + [CYC_START, CYC_END]:
        assert ws.cell(1, c).value is None
    # Exactly 21 columns: nothing in col 22.
    assert ws.cell(2, LAST_COL + 1).value is None

    assert {str(m) for m in ws.merged_cells.ranges} == EXPECTED_MERGES
    assert ws.auto_filter.ref == "A2:U4"

    # Detail row, then its sub-activity TOTAL. No employee grand total.
    d = _detail_row(ws, "E-1 - Test User", "FMTL", cycle_start)
    assert ws.cell(d, EMP).value == "E-1 - Test User"
    assert _cell_date(ws.cell(d, DATE_C).value) == cycle_start
    assert ws.cell(d, PROJECT).value == "P-1 - Test Project"
    assert ws.cell(d, ACTIVITY).value == "Activity for FMTL"
    assert ws.cell(d, SUB).value == "FMTL"
    assert ws.cell(d, ACH).value is None             # % only on the TOTAL row
    assert ws.cell(d, DIFF).value is None
    assert ws.cell(d, TGT_TAGS).value == 250
    assert ws.cell(d, TGT_DOCS).value is None
    assert ws.cell(d, ACT_TAGS).value == 200
    assert ws.cell(d, PEN_TAGS).value == 50
    assert _cell_date(ws.cell(d, CYC_START).value) == cycle_start
    assert _cell_date(ws.cell(d, CYC_END).value) == cycle_end

    t = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(t, EMP).value == "E-1 - Test User"    # repeated (filterable)
    assert ws.cell(t, DATE_C).value is None              # DATE blank on totals
    assert ws.cell(t, PROJECT).value == "TOTAL"          # marker in PROJECT col
    assert ws.cell(t, ACTIVITY).value == "Activity for FMTL"
    assert ws.cell(t, SUB).value == "FMTL"
    assert ws.cell(t, TGT_TAGS).value == 250
    assert ws.cell(t, ACT_TAGS).value == 200
    assert ws.cell(t, PEN_TAGS).value == 50
    assert ws.cell(t, ACH).value == 0.8
    assert ws.cell(t, ACH).number_format == "0.00%"
    assert ws.cell(t, DIFF).value == pytest.approx(0.2)
    assert ws.cell(t, DIFF).number_format == "0.00%"
    assert _fill(ws.cell(t, DIFF)) == RED
    # No employee grand total row and no current-cycle rows leaked in.
    assert len(_all_total_rows(ws)) == 1
    assert ws.max_row == 4


def test_no_employee_grand_total_is_generated(client, setup_author, activity_admin):
    """One employee with two numeric sub-activities gets one TOTAL per
    sub-activity and NO combined employee total."""
    a = setup_author()
    _, fmtl = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    _, mtl = _make_sub_activity(client, activity_admin, benchmark_value=100, name="MTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, fmtl["id"], cycle_start, 200)
    _submit(client, a["header"], a["project"].id, mtl["id"], day2, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    totals = _all_total_rows(ws)
    assert len(totals) == 2                                 # FMTL + MTL, nothing else
    # Every TOTAL row names its sub-activity (a grand total would leave it blank).
    assert all(ws.cell(r, SUB).value in ("FMTL", "MTL") for r in totals)


# --- export content ---------------------------------------------------------

def test_cycle_current_exports_the_active_cycle(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=120, name="FMTL")
    _submit(client, a["header"], a["project"].id, sub["id"], TODAY_D, 100)  # pending 20

    ws = _load_sheet(client.get(f"{EXPORT_URL}?cycle=current", headers=activity_admin).content)
    label = "E-1 - Test User"
    assert ws.cell(_detail_row(ws, label, "FMTL", TODAY_D), PEN_TAGS).value == 20
    total = _sub_total_row(ws, label, "FMTL")
    assert ws.cell(total, ACH).value == pytest.approx(100 / 120)   # 83.33%, uncapped-ready
    assert _fill(ws.cell(total, DIFF)) == RED


def test_employees_performance_cycle_param_switches_window(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 200)

    def rows(query: str = "") -> dict:
        res = client.get(f"/api/v1/benchmarks/employees-performance{query}", headers=activity_admin)
        assert res.status_code == 200
        return {r["employee_code"]: r for r in res.json()["items"]}

    current = rows()
    assert float(current["E-1"]["pending"]) == 0
    assert float(current["E-1"]["target"]) == 0

    prev = rows("?cycle=previous")
    assert float(prev["E-1"]["pending"]) == 50
    assert float(prev["E-1"]["target"]) == 250
    assert float(prev["E-1"]["actual"]) == 200

    assert client.get(
        "/api/v1/benchmarks/employees-performance?cycle=nope", headers=activity_admin
    ).status_code == 422


# --- numeric grouping / compensation ----------------------------------------

def test_fmtl_and_mtl_get_separate_sub_activity_totals(client, setup_author, activity_admin):
    a = setup_author()
    _, fmtl = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    _, mtl = _make_sub_activity(client, activity_admin, benchmark_value=100, name="MTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, fmtl["id"], cycle_start, 200)  # 80%
    _submit(client, a["header"], a["project"].id, mtl["id"], day2, 80)           # 80%

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    f_total = _sub_total_row(ws, label, "FMTL")
    m_total = _sub_total_row(ws, label, "MTL")
    assert f_total != m_total
    assert ws.cell(f_total, TGT_TAGS).value == 250 and ws.cell(f_total, ACH).value == 0.8
    assert ws.cell(m_total, TGT_TAGS).value == 100 and ws.cell(m_total, ACH).value == 0.8
    assert f_total < m_total  # sub-activities sort ascending: FMTL before MTL


def test_rows_sort_by_activity_then_sub_activity(client, setup_author, activity_admin):
    """Output order is employee -> activity -> sub-activity -> date. Two
    sub-activities whose names sort opposite to their activities prove the
    activity is the outer key."""
    a = setup_author()
    # Activity "A ..." owns the later-sorting sub-activity name, and vice versa.
    act_a = client.post(
        "/api/v1/activity-master/activities", json={"name": "AAA ACTIVITY"}, headers=activity_admin
    ).json()
    act_z = client.post(
        "/api/v1/activity-master/activities", json={"name": "ZZZ ACTIVITY"}, headers=activity_admin
    ).json()

    def sub_of(activity, name):
        return client.post(
            f"/api/v1/activity-master/activities/{activity['id']}/sub-activities",
            json={
                "name": name, "benchmark_type": "NUMERIC",
                "benchmark_value": 100, "relevant_count_field": "tags",
            },
            headers=activity_admin,
        ).json()

    z_named = sub_of(act_a, "ZZZ SUB")   # AAA ACTIVITY / ZZZ SUB
    a_named = sub_of(act_z, "AAA SUB")   # ZZZ ACTIVITY / AAA SUB
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, z_named["id"], cycle_start, 100)
    _submit(client, a["header"], a["project"].id, a_named["id"], day2, 100)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    # AAA ACTIVITY's rows come first even though its sub-activity name sorts last.
    assert _sub_total_row(ws, label, "ZZZ SUB") < _sub_total_row(ws, label, "AAA SUB")
    assert ws.cell(3, ACTIVITY).value == "AAA ACTIVITY"


def test_two_dates_of_one_sub_activity_combine_into_one_subtotal(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=200, name="FMTL")
    cycle_start, _ = _prev_cycle()
    day3 = cycle_start + timedelta(days=2)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 250)  # day1 250/200
    _submit(client, a["header"], a["project"].id, sub["id"], day3, 120)         # day3 120/200

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    assert len(_sub_total_rows(ws, label, "FMTL")) == 1
    total = _sub_total_row(ws, label, "FMTL")
    assert ws.cell(total, TGT_TAGS).value == 400        # 200 + 200
    assert ws.cell(total, ACT_TAGS).value == 370        # 250 + 120
    assert ws.cell(total, PEN_TAGS).value == 30         # max(0, 400 - 370), NOT 0 + 80
    assert ws.cell(total, ACH).value == pytest.approx(370 / 400)   # 92.50%
    assert ws.cell(_detail_row(ws, label, "FMTL", cycle_start), PEN_TAGS).value == 0
    assert ws.cell(_detail_row(ws, label, "FMTL", day3), PEN_TAGS).value == 80


def test_later_overachievement_offsets_earlier_shortage(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    monday = cycle_start + timedelta(days=3)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 100)  # short 150
    _submit(client, a["header"], a["project"].id, sub["id"], monday, 400)       # surplus 150

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    assert ws.cell(_detail_row(ws, label, "FMTL", cycle_start), PEN_TAGS).value == 150
    assert ws.cell(_detail_row(ws, label, "FMTL", monday), PEN_TAGS).value == 0
    total = _sub_total_row(ws, label, "FMTL")
    assert ws.cell(total, TGT_TAGS).value == 500
    assert ws.cell(total, ACT_TAGS).value == 500
    assert ws.cell(total, PEN_TAGS).value == 0     # NOT 150 (sum of daily shortages)
    assert ws.cell(total, ACH).value == 1.0
    # Exactly 100% is "met", not "ahead" -> no shade at all.
    assert ws.cell(total, DIFF).value == 0.0
    assert _fill(ws.cell(total, DIFF)) is None


def test_earlier_overachievement_offsets_later_shortage(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    monday = cycle_start + timedelta(days=3)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 400)  # surplus 150
    _submit(client, a["header"], a["project"].id, sub["id"], monday, 100)       # short 150

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    assert ws.cell(_detail_row(ws, label, "FMTL", cycle_start), PEN_TAGS).value == 0
    assert ws.cell(_detail_row(ws, label, "FMTL", monday), PEN_TAGS).value == 150
    total = _sub_total_row(ws, label, "FMTL")
    assert ws.cell(total, PEN_TAGS).value == 0
    assert ws.cell(total, ACH).value == 1.0
    assert _fill(ws.cell(total, DIFF)) is None


def test_fmtl_overachievement_does_not_offset_mtl_shortage(client, setup_author, activity_admin):
    """A surplus in FMTL must NOT pay down a shortfall in MTL, even though both
    count TAGS. Each sub-activity nets only itself."""
    a = setup_author()
    _, fmtl = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    _, mtl = _make_sub_activity(client, activity_admin, benchmark_value=100, name="MTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, fmtl["id"], cycle_start, 200)  # +100 FMTL
    _submit(client, a["header"], a["project"].id, mtl["id"], day2, 40)           # short 60 MTL

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    f_total = _sub_total_row(ws, label, "FMTL")
    m_total = _sub_total_row(ws, label, "MTL")
    assert ws.cell(f_total, PEN_TAGS).value == 0 and ws.cell(f_total, ACH).value == 2.0
    assert ws.cell(m_total, PEN_TAGS).value == 60 and ws.cell(m_total, ACH).value == 0.4


def test_tags_excess_does_not_offset_docs_shortage(client, setup_author, activity_admin):
    """Different benchmark units never compensate: a TAGS surplus must NOT offset
    a DOCS shortfall. Each lands in its own subtotal, netted per unit."""
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
    label = "E-1 - Test User"
    tagged = _sub_total_row(ws, label, "TAGGED")
    docd = _sub_total_row(ws, label, "DOCD")
    assert ws.cell(tagged, PEN_TAGS).value == 0 and ws.cell(tagged, ACH).value == 1.5
    assert ws.cell(docd, PEN_DOCS).value == 60 and ws.cell(docd, ACH).value == 0.4


def test_compensation_is_scoped_per_employee(client, setup_author, activity_admin):
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    over = setup_author(email="o@x.com", code="O-1", proj_code="PO", last_name="Over")
    _submit(client, over["header"], over["project"].id, sub["id"], cycle_start, 300)  # +200
    under = setup_author(email="u@x.com", code="U-1", proj_code="PU", last_name="Under")
    _submit(client, under["header"], under["project"].id, sub["id"], cycle_start, 40)  # short 60

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    u = _sub_total_row(ws, "U-1 - Test Under", "FMTL")
    assert ws.cell(u, PEN_TAGS).value == 60 and ws.cell(u, ACH).value == 0.4
    o = _sub_total_row(ws, "O-1 - Test Over", "FMTL")
    assert ws.cell(o, PEN_TAGS).value == 0 and ws.cell(o, ACH).value == 3.0


def test_percentage_uses_the_entire_cycle(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 120)  # over
    _submit(client, a["header"], a["project"].id, sub["id"], day2, 60)          # short

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(total, TGT_TAGS).value == 200
    assert ws.cell(total, ACT_TAGS).value == 180
    assert ws.cell(total, PEN_TAGS).value == 20
    assert ws.cell(total, ACH).value == 0.9


def test_achievement_uncapped_above_100_percent(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 175)  # 175%

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(total, PEN_TAGS).value == 0
    assert ws.cell(total, ACH).value == 1.75           # uncapped
    assert ws.cell(total, DIFF).value == pytest.approx(0.75)   # 220% -> 120%, no cap
    assert _fill(ws.cell(total, DIFF)) == GREEN


def test_employee_with_no_pending_is_still_exported(client, setup_author, activity_admin):
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 100)  # exactly met

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    total = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(total, PEN_TAGS).value == 0
    assert ws.cell(total, ACH).value == 1.0
    assert _fill(ws.cell(total, DIFF)) is None


# --- required acceptance cases: the three shade bands ------------------------

def test_acceptance_below_95_shades_difference_cell_red(client, setup_author, activity_admin):
    """Target 65 / actual 60 -> 92.31% achievement, 7.69% difference. The G cell
    alone is red; F and every other cell stay unfilled."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=65, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 60)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    t = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(t, ACH).value == pytest.approx(60 / 65)          # 92.31%
    assert ws.cell(t, DIFF).value == pytest.approx(1 - 60 / 65)     # 7.69%
    assert round(ws.cell(t, DIFF).value * 100, 2) == 7.69
    assert _fill(ws.cell(t, DIFF)) == RED
    assert _fill(ws.cell(t, ACH)) is None       # the decider is never shaded
    _assert_only_diff_cell_shaded(ws, t)


def test_acceptance_95_to_100_has_no_shade_anywhere(client, setup_author, activity_admin):
    """Target 100 / actual 97 -> 97.00%, 3.00% difference and NO fill at all."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 97)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    t = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(t, ACH).value == 0.97
    assert ws.cell(t, DIFF).value == pytest.approx(0.03)
    assert _fill(ws.cell(t, DIFF)) is None
    # The entire row carries no fill whatsoever.
    for c in range(1, LAST_COL + 1):
        assert _fill(ws.cell(t, c)) is None


def test_acceptance_above_100_shades_difference_cell_green(client, setup_author, activity_admin):
    """Target 400 / actual 500 -> 125.00% achievement, 25.00% difference. The G
    cell alone is green."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=200, name="FMTL")
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 250)
    _submit(client, a["header"], a["project"].id, sub["id"], day2, 250)   # 500 / 400

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    t = _sub_total_row(ws, "E-1 - Test User", "FMTL")
    assert ws.cell(t, TGT_TAGS).value == 400 and ws.cell(t, ACT_TAGS).value == 500
    assert ws.cell(t, ACH).value == 1.25
    assert ws.cell(t, DIFF).value == pytest.approx(0.25)
    assert _fill(ws.cell(t, DIFF)) == GREEN
    assert _fill(ws.cell(t, ACH)) is None
    _assert_only_diff_cell_shaded(ws, t)


def test_shade_boundaries_are_strict(client, setup_author, activity_admin):
    """94.99% red, 95.00% none, 100.00% none, 100.01% green — decided by F, worn
    by G."""
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=10000, name="FMTL")
    cycle_start, _ = _prev_cycle()
    cases = [
        ("R", 9499, RED),      # 94.99%
        ("N", 9500, None),     # 95.00% — exactly on the boundary, no shade
        ("M", 10000, None),    # 100.00% — met, no shade
        ("G", 10001, GREEN),   # 100.01%
    ]
    for code, actual, _expected in cases:
        emp = setup_author(
            email=f"{code}@x.com", code=f"{code}-1", proj_code=f"P{code}", last_name=code
        )
        _submit(client, emp["header"], emp["project"].id, sub["id"], cycle_start, actual)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    for code, actual, expected in cases:
        t = _sub_total_row(ws, f"{code}-1 - Test {code}", "FMTL")
        assert ws.cell(t, ACH).value == pytest.approx(actual / 10000)
        assert _fill(ws.cell(t, DIFF)) == expected, f"{code}: {actual / 100:.2f}%"
        assert _fill(ws.cell(t, ACH)) is None
        _assert_only_diff_cell_shaded(ws, t)


def test_no_full_row_is_ever_coloured(client, setup_author, activity_admin):
    """Across a mixed sheet (red, green, unshaded and textual rows), the ONLY
    filled body cells in the whole workbook are DIFFERENCE % cells."""
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    for code, actual in (("R", 80), ("G", 150), ("N", 97)):
        emp = setup_author(
            email=f"{code}@x.com", code=f"{code}-1", proj_code=f"P{code}", last_name=code
        )
        _submit(client, emp["header"], emp["project"].id, sub["id"], cycle_start, actual)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    filled = {
        ws.cell(r, c).coordinate: _fill(ws.cell(r, c))
        for r in range(3, ws.max_row + 1)
        for c in range(1, LAST_COL + 1)
        if _fill(ws.cell(r, c)) is not None
    }
    assert all(coord.startswith("G") for coord in filled), filled
    assert set(filled.values()) <= {RED, GREEN}


# --- sub_activity_id grouping + filter integrity ----------------------------

def test_grouping_keys_on_sub_activity_id_not_name(client, setup_author, activity_admin):
    """Two DISTINCT sub-activities sharing a displayed name stay apart (grouped
    by id) -> two subtotal rows, not one merged total."""
    a = setup_author()
    _, s1 = _make_sub_activity(client, activity_admin, benchmark_value=100, name="SHARED")
    _, s2 = _make_sub_activity(client, activity_admin, benchmark_value=100, name="SHARED")
    assert s1["id"] != s2["id"]
    cycle_start, _ = _prev_cycle()
    day2 = cycle_start + timedelta(days=1)
    _submit(client, a["header"], a["project"].id, s1["id"], cycle_start, 100)
    _submit(client, a["header"], a["project"].id, s2["id"], day2, 40)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    assert len(_sub_total_rows(ws, "E-1 - Test User", "SHARED")) == 2


def test_every_row_repeats_exact_employee_code_and_name(client, setup_author, activity_admin):
    a = setup_author(code="CDC002", first_name="RAMASRINIVASAMOORTHY", last_name="D")
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="MTL-ASSET PHOTO DATA POPULATION")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    expected = "CDC002 - RAMASRINIVASAMOORTHY D"
    detail = _detail_row(ws, expected, "MTL-ASSET PHOTO DATA POPULATION", cycle_start)
    total = _sub_total_row(ws, expected, "MTL-ASSET PHOTO DATA POPULATION")
    assert ws.cell(detail, EMP).value == expected
    assert ws.cell(total, EMP).value == expected


def test_filter_by_sub_activity_keeps_detail_and_subtotal(client, setup_author, activity_admin):
    """The TOTAL row repeats the exact sub-activity name (not a bare "TOTAL" in
    SUB ACTIVITY), so a sub-activity filter keeps both detail and its total."""
    a = setup_author(code="CDC002", first_name="RAMASRINIVASAMOORTHY", last_name="D")
    sub_name = "MTL-ASSET PHOTO DATA POPULATION"
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name=sub_name)
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    kept = [r for r in range(3, ws.max_row + 1) if ws.cell(r, SUB).value == sub_name]
    assert len(kept) == 2  # the detail row and its total row
    projects = {ws.cell(r, PROJECT).value for r in kept}
    assert projects == {"P-1 - Test Project", "TOTAL"}


# --- textual task rows: detail only, no total, no %, no shade ----------------

def test_textual_task_rows_have_no_total_or_percentage_mahesvari(
    client, db, setup_author, activity_admin,
):
    """Exact required case: a purely textual task sub-activity shows ONLY its
    dated detail rows — no subtotal, no percentages, no shading, no numeric
    totals."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author(code="CDCON064", first_name="MAHESVARI", last_name="S")
    sub_name = "BOM IDB-ADDRRESSING SPIR DOC AS PER MDR/PUNCH LIST FOR NOT AVAILABLE SPIR"
    _, task = _make_task_sub(client, activity_admin, name=sub_name)
    cycle_start, _ = _prev_cycle()
    d1, d2 = cycle_start, cycle_start + timedelta(days=1)
    for d in (d1, d2):
        tid = _submit_task(client, a["header"], a["project"].id, task["id"], d)
        row = db.get(WorkReportTask, uuid_mod.UUID(tid))
        row.due_date, row.is_completed, row.completed_date = d, True, d
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "CDCON064 - MAHESVARI S"

    # Exactly two rows for the sub-activity — both DETAIL, no total.
    sub_rows = [r for r in range(3, ws.max_row + 1) if ws.cell(r, SUB).value == sub_name]
    assert len(sub_rows) == 2
    assert _sub_total_rows(ws, label, sub_name) == []
    for r, d in zip(sub_rows, (d1, d2)):
        assert _cell_date(ws.cell(r, DATE_C).value) == d
        assert ws.cell(r, TGT_TAGS).value == "FINISH WITHIN A DAY"
        assert ws.cell(r, ACT_TAGS).value == "FINISHED"
        assert ws.cell(r, PEN_TAGS).value == "NO PENDING"
        assert ws.cell(r, ACH).value is None            # percentages blank
        assert ws.cell(r, DIFF).value is None
        assert _fill(ws.cell(r, DIFF)) is None          # and never shaded
        _assert_only_diff_cell_shaded(ws, r)
        # Textual rows keep normal detail-row styling.
        assert ws.cell(r, EMP).font.bold is False
        assert ws.cell(r, EMP).font.name == "Arial" and ws.cell(r, EMP).font.sz == 10
        assert ws.cell(r, EMP).border.top.style == "thin"
        # No numeric totals in any target/actual/pending unit cell.
        for c in (TGT_TAGS, ACT_TAGS, PEN_TAGS):
            assert not isinstance(ws.cell(r, c).value, (int, float))


def test_textual_status_variants_stay_textual_and_excluded(client, db, setup_author, activity_admin):
    """FINISH WITHIN 2 DAYS / NOT COMPLETED / N DAYS OVERDUE remain textual and
    never produce a subtotal or percentage."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, task = _make_task_sub(client, activity_admin, name="OVERDUE-TASK", period=2)
    cycle_start, cycle_end = _prev_cycle()
    tid = _submit_task(client, a["header"], a["project"].id, task["id"], cycle_start)
    row = db.get(WorkReportTask, uuid_mod.UUID(tid))
    row.due_date = cycle_end - timedelta(days=3)   # 3 days overdue as of cycle end
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    d = _detail_row(ws, label, "OVERDUE-TASK", cycle_start)
    assert ws.cell(d, TGT_TAGS).value == "FINISH WITHIN 2 DAYS"
    assert ws.cell(d, ACT_TAGS).value == "NOT COMPLETED"
    assert ws.cell(d, PEN_TAGS).value == "3 DAYS OVERDUE"
    assert ws.cell(d, ACH).value is None
    assert ws.cell(d, DIFF).value is None
    assert _sub_total_rows(ws, label, "OVERDUE-TASK") == []


def test_count_based_task_is_numeric_and_gets_a_subtotal(client, db, setup_author, activity_admin):
    """CASE A (count-based lumpsum with real numbers) is treated as numeric: its
    bare numbers feed a subtotal + %. A plain textual task alongside it gets
    none."""
    import uuid as uuid_mod

    from app.modules.activity_master.models import ActivityMaster
    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, count_sub = _make_task_sub(client, activity_admin, name="COUNT-LUMP")
    _, text_sub = _make_task_sub(client, activity_admin, name="TEXT-TASK")
    master = db.get(ActivityMaster, uuid_mod.UUID(count_sub["id"]))
    master.benchmark_value, master.relevant_count_field = 1000, "tags"
    db.commit()

    cycle_start, cycle_end = _prev_cycle()
    payload = {
        "report_date": cycle_start.isoformat(),
        "tasks": [
            {"project_id": str(a["project"].id), "description": "c",
             "sub_activity_id": count_sub["id"], "tags_count": 500},
            {"project_id": str(a["project"].id), "description": "t",
             "sub_activity_id": text_sub["id"]},
        ],
    }
    body = client.post(BASE, headers=a["header"], json=payload).json()
    assert client.post(f"{BASE}/{body['id']}/submit", headers=a["header"]).status_code == 200
    due = {count_sub["id"]: cycle_end - timedelta(days=5), text_sub["id"]: cycle_end - timedelta(days=3)}
    for t in body["tasks"]:
        row = db.get(WorkReportTask, uuid_mod.UUID(t["id"]))
        row.due_date = due[str(row.sub_activity_id)]
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    # Count-based lumpsum: text detail cells, numeric subtotal (500/1000 = 50%).
    dc = _detail_row(ws, label, "COUNT-LUMP", cycle_start)
    assert ws.cell(dc, TGT_TAGS).value == "1000 TAGS PER DAY"
    ct = _sub_total_row(ws, label, "COUNT-LUMP")
    assert ws.cell(ct, TGT_TAGS).value == 1000
    assert ws.cell(ct, ACT_TAGS).value == 500
    assert ws.cell(ct, ACH).value == 0.5
    assert ws.cell(ct, DIFF).value == pytest.approx(0.5)
    assert _fill(ws.cell(ct, DIFF)) == RED
    # Plain textual task: detail only, no subtotal.
    assert _sub_total_rows(ws, label, "TEXT-TASK") == []


def test_numeric_and_textual_mixed_employee(client, db, setup_author, activity_admin):
    """One employee with a NUMERIC sub-activity and a textual DONE task: the
    numeric one gets its subtotal, the textual one does not, and the completed
    task never moves the numeric %."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, num = _make_sub_activity(client, activity_admin, benchmark_value=100, name="NUM")
    _, done = _make_task_sub(client, activity_admin, name="DONE")
    cycle_start, _ = _prev_cycle()
    day1, day2, day3 = cycle_start, cycle_start + timedelta(days=1), cycle_start + timedelta(days=2)
    _submit(client, a["header"], a["project"].id, num["id"], day1, 200)  # over
    _submit(client, a["header"], a["project"].id, num["id"], day2, 80)   # short -> included
    tid = _submit_task(client, a["header"], a["project"].id, done["id"], day3)
    task = db.get(WorkReportTask, uuid_mod.UUID(tid))
    task.due_date, task.is_completed, task.completed_date = day3, True, day3
    db.commit()

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    num_total = _sub_total_row(ws, label, "NUM")
    assert ws.cell(num_total, ACH).value == 1.4        # (200+80)/(100+100)
    assert _sub_total_rows(ws, label, "DONE") == []    # textual DONE: no total
    d = _detail_row(ws, label, "DONE", day3)
    assert ws.cell(d, TGT_TAGS).value == "FINISH WITHIN A DAY"
    assert ws.cell(d, ACT_TAGS).value == "FINISHED"


def test_no_numeric_target_does_not_divide_by_zero(client, db, setup_author, activity_admin):
    """A plain textual task has no numeric target — export succeeds (no /0) and
    emits no subtotal for it."""
    import uuid as uuid_mod

    from app.modules.work_reports.models import WorkReportTask

    a = setup_author()
    _, task = _make_task_sub(client, activity_admin, name="PLAIN")
    cycle_start, cycle_end = _prev_cycle()
    tid = _submit_task(client, a["header"], a["project"].id, task["id"], cycle_start)
    row = db.get(WorkReportTask, uuid_mod.UUID(tid))
    row.due_date = cycle_end - timedelta(days=1)
    db.commit()

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200  # no ZeroDivisionError
    ws = _load_sheet(res.content)
    assert _sub_total_rows(ws, "E-1 - Test User", "PLAIN") == []


# --- Excel style regression (compare actual stored workbook properties) -------

def test_header_style_matches_reference(client, setup_author, activity_admin):
    """Yellow FFFFFF00 Arial 10 bold centred+wrapped with thin borders across the
    WHOLE A1:U2 block, including the blank cells above A:G and T:U."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)

    assert ws["A2"].fill.fill_type == "solid"
    assert ws["A2"].fill.fgColor.rgb == HEADER_YELLOW == _PB_HEADER_FILL.fgColor.rgb
    assert ws["A2"].font.name == "Arial" == _PB_HEADER_FONT.name
    assert ws["A2"].font.sz == 10
    assert ws["A2"].font.bold is True
    assert ws["A2"].alignment.horizontal == "center"
    assert ws["A2"].alignment.vertical == "center"

    # Every style-bearing header cell. Inside a merge only the anchor holds the
    # style — Excel paints it across the merged span — so the continuation cells
    # of H1:K1 / L1:O1 / P1:S1 are skipped, exactly as the reference stores them.
    merged_continuations = {
        c for c in range(TGT_TAGS, PEN_SPARES + 1)
        if c not in (TGT_TAGS, ACT_TAGS, PEN_TAGS)
    }
    for row in (1, 2):
        for c in range(1, LAST_COL + 1):
            if row == 1 and c in merged_continuations:
                continue
            cell = ws.cell(row, c)
            assert _fill(cell) == HEADER_YELLOW, cell.coordinate
            assert (cell.font.name, cell.font.sz, cell.font.bold) == ("Arial", 10, True)
            assert cell.alignment.horizontal == "center"
            assert cell.alignment.vertical == "center"
            assert cell.alignment.wrap_text is True
            for side in ("top", "bottom", "left", "right"):
                assert getattr(cell.border, side).style == "thin", f"{cell.coordinate}.{side}"


def test_worksheet_configuration_matches_reference(client, setup_author, activity_admin):
    """Sheet name, merges, freeze panes, filter range, row heights, widths."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)

    assert ws.title == "Pending Benchmark" == PENDING_SHEET_NAME
    assert {str(m) for m in ws.merged_cells.ranges} == EXPECTED_MERGES
    assert ws.freeze_panes == "A3"
    assert ws.auto_filter.ref.startswith("A2:")
    assert ws.auto_filter.ref == f"A2:U{ws.max_row}"
    assert ws.row_dimensions[1].height == 15.0
    assert ws.row_dimensions[2].height == 25.5
    assert ws.sheet_format.defaultRowHeight == 15.0
    for col, width in EXPECTED_WIDTHS.items():
        assert ws.column_dimensions[col].width == width, col


def test_detail_and_total_row_style_matches_reference(client, setup_author, activity_admin):
    """Detail rows: Arial 10 regular, no fill, top-aligned, thin borders, ISO
    dates. Total rows: identical but bold, with 0.00% on F and G."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=100, name="FMTL")
    cycle_start, _ = _prev_cycle()
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 80)  # 80% -> red

    ws = _load_sheet(client.get(EXPORT_URL, headers=activity_admin).content)
    label = "E-1 - Test User"
    d = _detail_row(ws, label, "FMTL", cycle_start)
    t = _sub_total_row(ws, label, "FMTL")

    for row, bold, font in ((d, False, _DATA_FONT), (t, True, _PB_TOTAL_FONT)):
        for c in range(1, LAST_COL + 1):
            cell = ws.cell(row, c)
            assert cell.font.name == font.name == "Arial", cell.coordinate
            assert cell.font.sz == 10
            assert cell.font.bold is bold, cell.coordinate
            assert cell.alignment.vertical == "top"
            # A:G and T:U left, the three unit groups (H:S) centered.
            expected_h = "center" if TGT_TAGS <= c <= PEN_SPARES else "left"
            assert cell.alignment.horizontal == expected_h, cell.coordinate
            for side in ("top", "bottom", "left", "right"):
                assert getattr(cell.border, side).style == _BORDER.top.style == "thin"

    for c in (DATE_C, CYC_START, CYC_END):
        assert ws.cell(d, c).number_format == "yyyy-mm-dd"
        assert ws.cell(t, c).number_format == "yyyy-mm-dd"
    assert ws.cell(t, ACH).number_format == "0.00%"
    assert ws.cell(t, DIFF).number_format == "0.00%"

    # Detail row is entirely unfilled; the total row shades only its G cell.
    for c in range(1, LAST_COL + 1):
        assert _fill(ws.cell(d, c)) is None, ws.cell(d, c).coordinate
    assert _fill(ws.cell(t, DIFF)) == RED
    _assert_only_diff_cell_shaded(ws, t)
