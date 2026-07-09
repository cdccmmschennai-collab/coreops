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


def _make_sub_activity(client, admin_header, *, benchmark_value, name="Sub"):
    a = client.post(
        "/api/v1/activity-master/activities", json={"name": f"Activity for {name}"}, headers=admin_header
    ).json()
    sub = client.post(
        f"/api/v1/activity-master/activities/{a['id']}/sub-activities",
        json={
            "name": name, "benchmark_type": "NUMERIC",
            "benchmark_value": benchmark_value, "relevant_count_field": "tags",
        },
        headers=admin_header,
    ).json()
    return a, sub


def _submit(client, header, project_id, sub_id, report_date, tags):
    payload = {
        "report_date": report_date.isoformat(),
        "tasks": [{
            "project_id": str(project_id), "description": "work",
            "sub_activity_id": sub_id, "tags_count": tags,
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
    assert f"pending-benchmark-{cycle_start.isoformat()}-to-{cycle_end.isoformat()}.xlsx" in (
        res.headers["content-disposition"]
    )

    ws = _load_sheet(res.content)
    # Two-row header: flat columns + three merged groups with unit sub-columns.
    assert [ws.cell(1, c).value for c in range(1, 6)] == [
        "Emp Code & Name", "Date", "Project", "Activity", "Sub Activity",
    ]
    assert ws.cell(1, 6).value == "Benchmark Target"
    assert ws.cell(1, 10).value == "Actual Completed"
    assert ws.cell(1, 14).value == "Pending Benchmark"
    assert ws.cell(1, 18).value == "Cycle Start"
    assert ws.cell(1, 19).value == "Cycle End"
    for start in (6, 10, 14):
        assert [ws.cell(2, start + i).value for i in range(4)] == ["Tags", "Docs", "BOM", "Spares"]
    merges = {str(r) for r in ws.merged_cells.ranges}
    assert {"F1:I1", "J1:M1", "N1:Q1", "A1:A2", "S1:S2"} <= merges

    # One data row (previous cycle only) then the employee TOTAL row.
    assert ws.cell(3, 1).value == "E-1 - Test User"
    assert _cell_date(ws.cell(3, 2).value) == cycle_start
    assert ws.cell(3, 5).value == "FMTL"
    assert ws.cell(3, 6).value == 250   # target -> Tags
    assert ws.cell(3, 7).value is None  # Docs stays blank
    assert ws.cell(3, 10).value == 200  # actual -> Tags
    assert ws.cell(3, 14).value == 50   # pending -> Tags
    assert _cell_date(ws.cell(3, 18).value) == cycle_start
    assert _cell_date(ws.cell(3, 19).value) == cycle_end

    assert ws.cell(4, 1).value is None
    assert ws.cell(4, 5).value == "TOTAL"
    assert ws.cell(4, 6).value == 250
    assert ws.cell(4, 10).value == 200
    assert ws.cell(4, 14).value == 50
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
    assert ws.cell(3, 14).value == 20
    assert ws.cell(4, 5).value == "TOTAL"


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


def test_recovered_deficit_is_reconciled_away_and_employee_excluded(
    client, setup_author, activity_admin,
):
    """A later day's surplus pays down an earlier deficit (frozen
    reconciliation); an employee with nothing left pending after that has no
    rows at all — the export is header-only."""
    a = setup_author()
    _, sub = _make_sub_activity(client, activity_admin, benchmark_value=250, name="FMTL")
    cycle_start, _ = _prev_cycle()
    monday = cycle_start + timedelta(days=3)
    _submit(client, a["header"], a["project"].id, sub["id"], cycle_start, 100)  # short 150
    _submit(client, a["header"], a["project"].id, sub["id"], monday, 400)       # surplus 150

    res = client.get(EXPORT_URL, headers=activity_admin)
    assert res.status_code == 200
    ws = _load_sheet(res.content)
    assert ws.max_row == 2  # header only — no data rows, no TOTAL row
