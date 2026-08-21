"""PM Weekly Activity Report — the one-row-per-activity Excel layout.

The old export laid a day's second activity out HORIZONTALLY ("Project Code 2",
"No. of Tags 2" …), which no Excel filter or pivot could reach. This proves the
replacement: one header row, one row per logical activity (half-day), the day's
shared identity merged vertically WITHOUT losing the value the filter needs, and
the three benchmark shapes — "120 TAGS" / "LS" / "LS - 300 SPARES" — rendered
from the snapshot frozen on the task.

Nothing here recomputes a benchmark: `benchmark_display` reads benchmark_type /
benchmark_value / benchmark_unit exactly as work_report_tasks froze them.
"""
from datetime import date

import openpyxl
import pytest

from app.modules.reports_export import export

MONDAY = date(2026, 8, 17)


def _activity(**over):
    base = {
        "day_part": "full_day",
        "period_status": None,
        "project_code": "P-1",
        "activity_type": "MTL",
        "sub_activity_type": "MTL-DATA POPULATION",
        "tags": 0, "docs": 0, "bom": 0, "spares": 0, "pages": 0, "records": 0,
        "benchmark_type": None,
        "benchmark_value": None,
        "benchmark_unit": None,
    }
    base.update(over)
    return base


def _day(*activities, **over):
    row = {
        "employee_label": "CDC019 - Arthi S",
        "report_date": MONDAY,
        "day_status": "Work at Office",
        "remarks": "worked on the idb",
        "activities": list(activities),
    }
    row.update(over)
    return row


def _sheet(rows):
    return openpyxl.load_workbook(export.build_workbook(rows)).active


def _cells(ws):
    """{(row, HEADER): value} — the sheet addressed by column name."""
    headers = {c.column: c.value for c in ws[1]}
    return {
        (c.row, headers[c.column]): c.value
        for row in ws.iter_rows(min_row=2)
        for c in row
    }


# ── benchmark rendering (pure) ───────────────────────────────────────────────


@pytest.mark.parametrize(
    ("benchmark_type", "value", "unit", "expected"),
    [
        # CASE 1 — count-based: the target with its own unit.
        ("NUMERIC_DAILY", 120, "tags", "120 TAGS"),
        ("NUMERIC", 176, "spares", "176 SPARES"),
        # CASE 2 — lumpsum with no quantity at all.
        ("TASK_STATUS_ONLY", None, None, "LS"),
        ("TASK_BASED", None, None, "LS"),
        # CASE 3 — lumpsum that DOES carry a quantity: the count must survive.
        ("TASK_WITH_QUANTITY", 300, "spares", "LS - 300 SPARES"),
        ("TASK_WITH_QUANTITY", 120, "tags", "LS - 120 TAGS"),
        ("TASK_WITH_QUANTITY", 50, "records", "LS - 50 RECORDS"),
        # No benchmark configured (e.g. LEAVE, TRAINING) — an empty cell.
        (None, None, None, None),
    ],
)
def test_benchmark_display_shapes(benchmark_type, value, unit, expected):
    assert export.benchmark_display(
        _activity(benchmark_type=benchmark_type, benchmark_value=value, benchmark_unit=unit)
    ) == expected


def test_lumpsum_with_a_quantity_never_collapses_to_bare_ls():
    """The requirement that is easiest to lose: an LS activity that has a count
    must print the count, in exactly 'LS - <COUNT> <UNIT>' form."""
    out = export.benchmark_display(
        _activity(benchmark_type="TASK_WITH_QUANTITY", benchmark_value=300, benchmark_unit="spares")
    )
    assert out == "LS - 300 SPARES"
    assert out != "LS"
    assert out not in ("LS 300", "300 LS", "Lumpsum - 300 Spares")


def test_benchmark_quantity_is_whole_where_it_is_whole():
    """A 300 target reads '300 SPARES', never '300.0 SPARES'. A genuinely
    fractional stored target is shown as it is rather than silently rounded."""
    whole = _activity(benchmark_type="NUMERIC_DAILY", benchmark_value=300.0, benchmark_unit="spares")
    assert export.benchmark_display(whole) == "300 SPARES"
    half = _activity(benchmark_type="NUMERIC_DAILY", benchmark_value=32.5, benchmark_unit="tags")
    assert export.benchmark_display(half) == "32.5 TAGS"


# ── HALF labelling ───────────────────────────────────────────────────────────


def test_half_label_follows_the_recorded_period_when_there_is_one():
    # Two tasks logged in the SAME recorded half both read FIRST HALF — the
    # period is authoritative, so nothing is renumbered behind the employee.
    assert export.half_label("first_half", 0, 2) == "FIRST HALF"
    assert export.half_label("first_half", 1, 2) == "FIRST HALF"
    assert export.half_label("second_half", 1, 2) == "SECOND HALF"


def test_half_label_falls_back_to_position_on_a_full_day_period():
    assert export.half_label("full_day", 0, 1) == "FULL DAY"
    assert export.half_label(None, 0, 1) == "FULL DAY"      # legacy, no period
    assert export.half_label("full_day", 0, 2) == "FIRST HALF"
    assert export.half_label("full_day", 1, 2) == "SECOND HALF"
    # A third activity has no half to be; it is numbered, not mislabelled.
    assert export.half_label("full_day", 2, 3) == "ACTIVITY 3"


# ── sheet structure ──────────────────────────────────────────────────────────


def test_single_header_row_with_autofilter_and_frozen_panes():
    ws = _sheet([_day(_activity())])
    assert ws.freeze_panes == "A2"
    assert ws.auto_filter.ref == "A1:P2"
    # Exactly one header row: no employee banner, no repeat further down.
    assert ws.cell(1, 1).value == "EMPLOYEE ID & NAME"
    assert ws.cell(2, 1).value != "EMPLOYEE ID & NAME"


def test_two_activities_become_two_rows_first_then_second_half():
    """CASE 5 + CASE 6 — the structural change. Two activities on one day are
    two rows, each keeping its own project, so both stay filterable."""
    ws = _sheet([_day(
        _activity(day_part="first_half", project_code="PROJECT A",
                  sub_activity_type="TAGGING", tags=120,
                  benchmark_type="NUMERIC_DAILY", benchmark_value=120, benchmark_unit="tags"),
        _activity(day_part="second_half", project_code="PROJECT B",
                  sub_activity_type="SUPPORT", benchmark_type="TASK_STATUS_ONLY"),
    )])
    c = _cells(ws)
    assert ws.max_row == 3
    assert c[(2, "HALF")] == "FIRST HALF"
    assert c[(3, "HALF")] == "SECOND HALF"
    assert c[(2, "PROJECT CODE")] == "PROJECT A"
    assert c[(3, "PROJECT CODE")] == "PROJECT B"
    assert c[(2, "BENCHMARK")] == "120 TAGS"
    assert c[(3, "BENCHMARK")] == "LS"
    assert c[(2, "NO. OF TAGS")] == 120
    assert c[(3, "NO. OF TAGS")] == 0


def test_one_activity_produces_one_row_and_no_blank_half():
    ws = _sheet([_day(_activity())])
    assert ws.max_row == 2
    assert _cells(ws)[(2, "HALF")] == "FULL DAY"


def test_day_identity_is_merged_but_every_cell_keeps_its_value():
    """The merge is visual only. Excel's AutoFilter reads the underlying cell,
    so blanking the second-half row would drop it from an 'Employee = X' filter
    — the exact failure this guards."""
    ws = _sheet([_day(
        _activity(day_part="first_half"), _activity(day_part="second_half")
    )])
    merged = {str(r) for r in ws.merged_cells.ranges}
    assert {"A2:A3", "B2:B3", "C2:C3", "D2:D3", "P2:P3"} <= merged
    # The activity columns are NEVER merged — they must stay individually
    # filterable and sortable.
    assert not [m for m in merged if m[0] in "EFGHIJKLMNO"]
    # openpyxl masks a merged follower on read; the written cell still holds it.
    written = {c.coordinate: c.value for c in ws["A"]}
    assert written["A2"] == "CDC019 - ARTHI S"


def test_day_status_is_not_merged_when_the_halves_differ():
    ws = _sheet([_day(
        _activity(day_part="first_half", period_status="Work at Office"),
        _activity(day_part="second_half", period_status="Leave"),
    )])
    c = _cells(ws)
    assert c[(2, "DAY STATUS")] == "WORK AT OFFICE"
    assert c[(3, "DAY STATUS")] == "LEAVE"
    assert "D2:D3" not in {str(r) for r in ws.merged_cells.ranges}


def test_leave_day_shows_leave_and_no_activity_detail():
    """CASE 4 — a day with no task lines at all."""
    ws = _sheet([_day(day_status="Leave", remarks=None)])
    c = _cells(ws)
    assert ws.max_row == 2
    assert c[(2, "DAY STATUS")] == "LEAVE"
    assert c[(2, "ACTIVITY TYPE")] == "LEAVE"
    assert c[(2, "HALF")] == "FULL DAY"
    # No project, sub-activity, counts or benchmark are invented for a day that
    # was not worked.
    for header in ("PROJECT CODE", "SUB ACTIVITY TYPE", "BENCHMARK",
                   "NO. OF TAGS", "NO. OF SPARES", "DAY REMARKS"):
        assert c[(2, header)] is None


def test_day_and_date_columns():
    ws = _sheet([_day(_activity())])
    c = _cells(ws)
    assert c[(2, "DAY")] == "MONDAY"  # 2026-08-17 is a Monday
    # A real Excel date, not text (openpyxl reads one back as a datetime).
    assert c[(2, "DATE")].date() == MONDAY
    assert ws.cell(2, 2).number_format == "yyyy-mm-dd"


def test_every_text_cell_is_uppercase():
    """CASE 7. Numbers and dates are left alone — uppercasing those would be
    meaningless at best and destructive at worst."""
    ws = _sheet([_day(
        _activity(day_part="first_half", project_code="p-1", activity_type="mtl",
                  sub_activity_type="mtl-data population", tags=51,
                  benchmark_type="NUMERIC_DAILY", benchmark_value=50, benchmark_unit="tags"),
        _activity(day_part="second_half", project_code="p-2", activity_type="doc idb"),
    )])
    for row in ws.iter_rows():
        for cell in row:
            if isinstance(cell.value, str):
                assert cell.value == cell.value.upper(), cell.coordinate
    c = _cells(ws)
    assert c[(2, "EMPLOYEE ID & NAME")] == "CDC019 - ARTHI S"
    assert c[(2, "SUB ACTIVITY TYPE")] == "MTL-DATA POPULATION"
    assert c[(2, "NO. OF TAGS")] == 51          # the count is untouched


def test_multiple_employees_share_one_continuous_table():
    """No per-employee banner or repeated header — those made the old sheet
    unfilterable as a single range."""
    rows = [
        _day(_activity(), employee_label="CDC019 - Arthi S"),
        _day(_activity(), employee_label="CDC021 - Yuva Shree"),
    ]
    ws = _sheet(rows)
    assert ws.max_row == 3
    assert ws.auto_filter.ref == "A1:P3"
    assert [ws.cell(r, 1).value for r in (2, 3)] == [
        "CDC019 - ARTHI S", "CDC021 - YUVA SHREE",
    ]


def test_empty_report_still_produces_a_usable_header():
    ws = _sheet([])
    assert ws.max_row == 1
    assert ws.auto_filter.ref == "A1:P1"
