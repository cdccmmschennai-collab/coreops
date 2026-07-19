"""Weekly Activity Report XLSX builder.

One layout: one row per Employee + Date, with dynamic activity column groups
(Project Code, … then 2, 3 …) repeated up to the max activities recorded on any
single day. The preview (flat rows) and this export share the same flat data,
but the export adds per-employee sections so each block is self-contained: a
merged employee title row, the full column header row, that employee's data
rows, then a blank spacer row before the next employee. With a single employee
the title/spacer are omitted and one header sits at the top.

Styling mirrors the company template: Arial 10 bold white header on teal
(FF76A5AF), thin borders, centered count columns, wrapped Day Remarks, real
Excel dates. Employee title rows are bold on a light teal tint (FFD9E2E1).
Sheet: 'Weekly Activity Report'."""
from decimal import Decimal
from io import BytesIO
from itertools import groupby

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

SHEET_NAME = "Weekly Activity Report"

_HEADER_FILL = PatternFill(fill_type="solid", fgColor="FF76A5AF")
_HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
_GROUP_FILL = PatternFill(fill_type="solid", fgColor="FFD9E2E1")
_GROUP_FONT = Font(name="Arial", size=10, bold=True)
_DATA_FONT = Font(name="Arial", size=10)
_THIN = Side(style="thin")
_BORDER = Border(top=_THIN, bottom=_THIN, left=_THIN, right=_THIN)

# One activity block: (label, width, centered).
_BLOCK = [
    ("Project Code", 16.4, False),
    ("Activity Type", 22.7, False),
    ("Sub Activity Type", 22.0, False),
    ("No. of Tags", 11.0, True),
    ("No. of Docs", 11.0, True),
    ("No. of BOM HEADER", 16.0, True),
    ("No. of Spares", 12.0, True),
]
_FIXED_LEFT = [
    ("Employee ID & Name", 24.0, False),
    ("Date", 12.0, False),
    ("Day Status", 11.0, False),
]
_REMARKS = ("Day Remarks", 68.4, False)


def date_range_label(start, end) -> str:
    """Human filename range like "03 JUL - 09 JUL" (zero-padded day, uppercase
    month), used in the download filenames of both XLSX exports."""
    return f"{start.strftime('%d %b').upper()} - {end.strftime('%d %b').upper()}"


def _new_sheet():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = SHEET_NAME
    return wb, ws


def _write_header(ws, row: int, columns: list[tuple[str, float, bool]]) -> None:
    for idx, (label, width, center) in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=idx, value=label)
        cell.font = _HEADER_FONT
        cell.fill = _HEADER_FILL
        cell.border = _BORDER
        cell.alignment = Alignment(horizontal="center" if center else "left", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width


def _write_group_header(ws, row: int, total_cols: int, label: str) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=total_cols)
    for col in range(1, total_cols + 1):
        c = ws.cell(row=row, column=col)
        c.fill = _GROUP_FILL
        c.border = _BORDER
    head = ws.cell(row=row, column=1, value=label)
    head.font = _GROUP_FONT
    head.alignment = Alignment(horizontal="left", vertical="center")


def _style_data_cell(cell, center: bool, wrap: bool, is_date: bool) -> None:
    cell.font = _DATA_FONT
    cell.border = _BORDER
    cell.alignment = Alignment(
        horizontal="center" if center else "left", vertical="top", wrap_text=wrap
    )
    if is_date:
        cell.number_format = "yyyy-mm-dd"


def _finalize(wb) -> BytesIO:
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


PENDING_SHEET_NAME = "Pending Benchmark"

# --- Benchmark report styling — matched cell-for-cell to the company reference
# workbook (BENCHMARK REPORT 03 JUL - 09 JUL). Only three colours exist in this
# sheet: the yellow header, and the green/red shade on the DIFFERENCE % cell.
# Everything else is white/no fill with black Arial 10 text and thin borders.
_PB_HEADER_FILL = PatternFill(fill_type="solid", fgColor="FFFFFF00")
# No colour= -> automatic (black), exactly as the reference stores it.
_PB_HEADER_FONT = Font(name="Arial", size=10, bold=True)
_PB_TOTAL_FONT = Font(name="Arial", size=10, bold=True)
# DIFFERENCE % cell shade, keyed off ACHIEVEMENT %. Nothing else is ever shaded.
_DIFF_GREEN = PatternFill(fill_type="solid", fgColor="FFC6EFCE")  # > 100%: ahead
_DIFF_RED = PatternFill(fill_type="solid", fgColor="FFFFC7CE")    # < 95%: needs attention
_PB_HEADER_ROW_HEIGHT = {1: 15.0, 2: 25.5}
_PB_DEFAULT_ROW_HEIGHT = 15.0

# Final column order (29 columns, A..AC): the identity columns — DAY PART
# directly after DATE — with the two percentage columns early (so they read
# beside the activity rather than off past the wide SUB ACTIVITY / PROJECT
# cells), then REMARKS, PROJECT, the three 6-unit groups, then the cycle
# bounds. No ROW TYPE, no per-group TOTAL sub-column, no EMPLOYEE TOTAL.
#
# Widths travel with the SEMANTIC field, not with a column letter: SUB ACTIVITY
# keeps 118.140625 and PROJECT keeps 86.0 wherever they sit.
_PB_LEFT = [
    ("EMP CODE & NAME", 26.0),
    ("DATE", 12.0),
    # Wide enough for its longest value, "HALF DAY (LEGACY)".
    ("DAY PART", 18.0),
    ("ACTIVITY", 22.0),
    ("ACHIEVEMENT %", 18.85546875),
    ("DIFFERENCE %", 15.0),
    ("SUB ACTIVITY", 118.140625),
    ("REMARKS", 50.0),
    ("PROJECT CODE & TITLE", 86.0),
]
_PB_DATE_COL = 2      # DATE
# DAY PART — FULL DAY / FIRST HALF / SECOND HALF / HALF DAY (LEGACY), repeated
# on every detail row of its period (never merged). Blank on a TOTAL row: a
# total spans the cycle, not one period.
_PB_DAY_PART_COL = 3
_PB_ACTIVITY_COL = 4  # ACTIVITY
_PB_ACH_COL = 5       # ACHIEVEMENT % — decides the shade, never wears it
_PB_DIFF_COL = 6      # DIFFERENCE % — the only shaded cell in the body
_PB_SUB_COL = 7       # SUB ACTIVITY
# REMARKS — the remark belonging to the row's OWN period (header remark for
# FULL DAY / HALF DAY (LEGACY), that half's period remark for FIRST/SECOND
# HALF), repeated on every detail row so a filtered row still reads on its
# own. Blank on a TOTAL row: a total spans the cycle, not one specific day.
# Never carries Activity Master's benchmark_remarks.
_PB_REMARKS_COL = 8
_PB_PROJECT_COL = 9   # PROJECT CODE & TITLE — carries the "TOTAL" marker
_PB_GROUPS = ["BENCHMARK TARGET", "ACTUAL COMPLETED", "PENDING BENCHMARK"]
# ledger benchmark_unit values — must stay in the same order as, and cover every
# value of, activity_master.models.COUNT_FIELD_BY_UNIT: a unit missing here has
# no column and its rows would silently land nowhere.
_PB_UNITS = ["tags", "docs", "bom", "spares", "pages", "records"]
_PB_UNIT_LABELS = ["TAGS", "DOCS", "BOM", "SPARES", "PAGES", "RECORDS"]  # no group total
_PB_GROUP_WIDTH = len(_PB_UNIT_LABELS)  # 6 columns per group
# Per-group unit widths: the leading TAGS column is widened to carry the merged
# group label above it; the rest stay 12.
_PB_UNIT_WIDTHS = [
    [21.42578125, 12.0, 12.0, 12.0, 12.0, 12.0],  # BENCHMARK TARGET  J:O
    [16.85546875, 12.0, 12.0, 12.0, 12.0, 12.0],  # ACTUAL COMPLETED  P:U
    [17.7109375, 12.0, 12.0, 12.0, 12.0, 12.0],   # PENDING BENCHMARK V:AA
]
_PB_RIGHT = [("CYCLE START", 13.0), ("CYCLE END", 13.0)]
_PB_NUMFMT_PCT = "0.00%"


def _difference_fill(achievement):
    """Shade for the DIFFERENCE % cell, chosen from the ACHIEVEMENT % fraction
    (1.0 == 100%). Strict boundaries: <95% red, 95%..100% inclusive no shade,
    >100% green. `None` (no numeric target — a textual task row) never shades.

    This fill lands on the DIFFERENCE % cell ONLY. The ACHIEVEMENT % cell that
    decides it, and every other cell on the row, stay unfilled."""
    if achievement is None:
        return None
    if achievement > 1.0:
        return _DIFF_GREEN
    if achievement < 0.95:
        return _DIFF_RED
    return None


def _is_numeric(value) -> bool:
    """Strict numeric-value check: a genuine number, never a status string.

    Only genuinely numeric benchmark values feed the totals and the achievement
    %. Textual task cells ("FINISH WITHIN A DAY", "FINISHED", "NO PENDING",
    "N DAYS OVERDUE", "NOT COMPLETED", ...) are strings and are excluded — they
    are never coerced to zero and never create a subtotal."""
    return isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)


def build_pending_benchmark_workbook(
    rows: list[dict], cycle_start, cycle_end
) -> BytesIO:
    """Full-cycle Benchmark XLSX, grouped employee -> sub-activity.

    Layout, styling, colours, fonts, borders, number formats, column widths,
    merged header cells, freeze panes and AutoFilter are matched cell-for-cell
    to the company reference workbook. Within an employee, each sub-activity's
    date-wise detail rows are followed by ONE bold TOTAL row for that exact
    sub-activity (never one combined per-employee total). Two distinct
    behaviours, decided per row by whether its benchmark value is genuinely
    numeric (see _is_numeric), NOT by benchmark_type:

    - A NUMERIC sub-activity (NUMERIC ledger days, or a count-based lumpsum with
      real numbers) gets its detail rows plus one TOTAL row carrying the
      sub-activity's per-unit target/actual/net-pending, its ACHIEVEMENT % and
      its DIFFERENCE %.
    - A purely TEXTUAL task sub-activity ("FINISH WITHIN A DAY" / "FINISHED" /
      "NO PENDING", etc.) shows its detail rows ONLY — no TOTAL row, no
      percentages, no shading, no participation in any numeric total.

    The TOTAL row repeats the exact EMP CODE & NAME, ACTIVITY and SUB ACTIVITY
    of its detail rows (so an Excel employee filter, or a sub-activity filter,
    keeps both the detail rows and the total), writes "TOTAL" in the PROJECT
    column, and leaves DATE blank. Its PENDING columns net the whole cycle per
    unit (MAX(0, cycle_target - cycle_actual)) rather than summing the daily
    shortages, so a day's overachievement offsets another day's shortfall — but
    only within the same employee + sub-activity + unit. Nothing crosses
    sub-activities, units, employees or cycles.

    ACHIEVEMENT % = total_actual / total_target summed across the six units,
    uncapped, formatted 0.00%; blank when total_target is 0 (no divide by zero).
    DIFFERENCE % = ABS(achievement - 100%), formatted 0.00%, blank whenever
    ACHIEVEMENT % is. Only the DIFFERENCE % cell is ever shaded (see
    _difference_fill) — never the achievement cell, never a full row.

    Header is two rows: row 1 carries ONLY the merged group labels, row 2 the
    real per-column header the AutoFilter anchors on. `rows` must arrive sorted
    employee -> activity -> sub-activity -> date -> project (the service
    guarantees it)."""
    wb, ws = _new_sheet()
    ws.title = PENDING_SHEET_NAME

    n_left = len(_PB_LEFT)
    n_units = len(_PB_UNITS)
    first_right = n_left + 1 + len(_PB_GROUPS) * _PB_GROUP_WIDTH  # first CYCLE column
    total_cols = first_right + len(_PB_RIGHT) - 1
    date_cols = {_PB_DATE_COL, first_right, first_right + 1}

    def group_start(gi: int) -> int:
        return n_left + 1 + gi * _PB_GROUP_WIDTH

    for idx, (label, width) in enumerate(_PB_LEFT, start=1):
        ws.cell(2, idx, label)
        ws.column_dimensions[get_column_letter(idx)].width = width
    for gi, group in enumerate(_PB_GROUPS):
        start = group_start(gi)
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=start + n_units - 1)
        ws.cell(1, start, group)
        for ui, unit_label in enumerate(_PB_UNIT_LABELS):
            ws.cell(2, start + ui, unit_label)
            ws.column_dimensions[get_column_letter(start + ui)].width = _PB_UNIT_WIDTHS[gi][ui]
    for ri, (label, width) in enumerate(_PB_RIGHT):
        col = first_right + ri
        ws.cell(2, col, label)
        ws.column_dimensions[get_column_letter(col)].width = width
    # Yellow header across the FULL A1:AC2 block — the cells left blank above the
    # identity/cycle columns carry the same style as the labelled ones.
    for row in (1, 2):
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = _PB_HEADER_FONT
            cell.fill = _PB_HEADER_FILL
            cell.border = _BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[row].height = _PB_HEADER_ROW_HEIGHT[row]
    ws.freeze_panes = "A3"
    ws.sheet_format.defaultRowHeight = _PB_DEFAULT_ROW_HEIGHT

    def style_row(r: int, bold: bool = False) -> None:
        """Body style: Arial 10, thin borders all round, vertical top, no fill.
        A:I and AB:AC left, the three unit groups (J:AA) centered. Bold on a
        TOTAL row. No fill is applied here — the DIFFERENCE % cell is shaded by
        its writer and is the only shaded body cell."""
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=col)
            _style_data_cell(cell, n_left < col < first_right, False, col in date_cols)
            if bold:
                cell.font = _PB_TOTAL_FONT
        # Free-text day remarks wrap instead of spilling across the unit columns.
        remarks_cell = ws.cell(row=r, column=_PB_REMARKS_COL)
        remarks_cell.alignment = Alignment(
            horizontal="left", vertical="top", wrap_text=True
        )

    unit_col = {u: i for i, u in enumerate(_PB_UNITS)}

    def write_sub_total_row(
        r: int, *, emp_label: str, activity: str, sub_activity: str, totals, used,
    ) -> None:
        """One bold TOTAL row for a numeric sub-activity. Nets each unit's cycle
        pending in place (MAX(0, target - actual)), then writes the per-unit
        target/actual/pending sums, the uncapped ACHIEVEMENT % and the
        DIFFERENCE % — shading the DIFFERENCE % cell alone. Repeats the exact
        emp/activity/sub-activity, writes "TOTAL" in PROJECT, leaves DATE,
        DAY PART and REMARKS blank (a total spans the cycle, not one specific
        day or period)."""
        for ui in range(n_units):
            totals[2][ui] = max(0.0, totals[0][ui] - totals[1][ui])
        ws.cell(r, 1, emp_label)                        # exact CODE - NAME (filterable)
        # DATE (col _PB_DATE_COL) stays blank on the total row.
        ws.cell(r, _PB_PROJECT_COL, "TOTAL")            # PROJECT column marks the total
        ws.cell(r, _PB_ACTIVITY_COL, activity)          # exact activity name
        ws.cell(r, _PB_SUB_COL, sub_activity)           # exact sub-activity name (filterable)
        for gi in range(len(_PB_GROUPS)):
            for ui in range(n_units):
                if used[ui]:
                    ws.cell(r, group_start(gi) + ui, totals[gi][ui])
        ws.cell(r, first_right, cycle_start)
        ws.cell(r, first_right + 1, cycle_end)
        style_row(r, bold=True)

        total_target = sum(totals[0])
        total_actual = sum(totals[1])
        # Uncapped actual/target; blank when target is 0 -> N/A, never a /0.
        achievement = (total_actual / total_target) if total_target > 0 else None
        if achievement is None:
            return
        ach_cell = ws.cell(r, _PB_ACH_COL, achievement)
        ach_cell.number_format = _PB_NUMFMT_PCT
        # Distance from target in either direction: 125% and 75% both read 25%.
        # Rounded well past the 2dp the cell shows, purely to keep binary-float
        # noise (0.3999999999999999) out of the formula bar.
        diff_cell = ws.cell(r, _PB_DIFF_COL, round(abs(achievement - 1.0), 10))
        diff_cell.number_format = _PB_NUMFMT_PCT
        # The ONLY shaded cell in the body of the sheet.
        fill = _difference_fill(achievement)
        if fill is not None:
            diff_cell.fill = fill

    r = 3
    for _emp_label, emp_rows in groupby(rows, key=lambda x: x["employee_label"]):
        for _gkey, sub_rows in groupby(emp_rows, key=lambda x: x["group_key"]):
            sub_rows = list(sub_rows)
            totals = [[0.0] * n_units for _ in _PB_GROUPS]
            used = [False] * n_units
            # All rows in a group share one sub_activity_id -> one activity name
            # and one exact sub-activity name; take them from the first row.
            activity = sub_rows[0]["activity"]
            sub_activity = sub_rows[0]["sub_activity"]

            for row in sub_rows:
                ws.cell(r, 1, row["employee_label"])
                ws.cell(r, _PB_DATE_COL, row["date"])
                # Repeated (never merged) on every row of the period, so a
                # filtered row still names its own part of the day.
                ws.cell(r, _PB_DAY_PART_COL, row.get("day_part") or None)
                ws.cell(r, _PB_PROJECT_COL, row["project"])
                ws.cell(r, _PB_ACTIVITY_COL, row["activity"])
                ws.cell(r, _PB_SUB_COL, row["sub_activity"])
                # Repeated on every detail row of this employee+date: the sheet
                # is filterable, so a row must read on its own.
                ws.cell(r, _PB_REMARKS_COL, row.get("day_remarks") or None)
                # ACHIEVEMENT % / DIFFERENCE % stay blank on every detail row.
                ui = unit_col.get(row["unit"])
                if ui is not None:
                    for gi, key in enumerate(("target", "actual", "pending")):
                        value = row[key]
                        ws.cell(
                            r,
                            group_start(gi) + ui,
                            value if isinstance(value, str) else float(value),
                        )
                    # Accumulate cycle target/actual only, and only for genuinely
                    # numeric benchmark values; the pending is derived from them
                    # on the total row so a day's overachievement nets another
                    # day's shortfall per unit. Textual task cells are skipped.
                    for gi, key in enumerate(("target", "actual")):
                        total_value = row[f"{key}_total"]
                        if _is_numeric(total_value):
                            totals[gi][ui] += float(total_value)
                            used[ui] = True
                ws.cell(r, first_right, cycle_start)
                ws.cell(r, first_right + 1, cycle_end)
                style_row(r)
                r += 1

            # A numeric sub-activity gets exactly one TOTAL row; a purely textual
            # task group (no genuinely numeric value in any row) gets NONE.
            if any(used):
                write_sub_total_row(
                    r, emp_label=sub_rows[0]["employee_label"], activity=activity,
                    sub_activity=sub_activity, totals=totals, used=used,
                )
                r += 1

    # Filter on the flattened header row (2) across all data rows.
    ws.auto_filter.ref = f"A2:{get_column_letter(total_cols)}{max(r - 1, 2)}"

    return _finalize(wb)


def build_workbook(rows: list[dict], max_activities: int) -> BytesIO:
    wb, ws = _new_sheet()

    # Columns: Employee | Date | Day Status | (block × max) | Day Remarks.
    columns = list(_FIXED_LEFT)
    for i in range(1, max_activities + 1):
        suffix = "" if i == 1 else f" {i}"
        for label, width, center in _BLOCK:
            columns.append((f"{label}{suffix}", width, center))
    columns.append(_REMARKS)
    total_cols = len(columns)
    centers = {idx for idx, (_, _, c) in enumerate(columns, start=1) if c}
    remarks_col = total_cols
    n_left = len(_FIXED_LEFT)

    def write_data_row(r: int, row: dict) -> None:
        ws.cell(r, 1, row["employee_label"])
        ws.cell(r, 2, row["report_date"])
        ws.cell(r, 3, row["day_status"])
        for i, act in enumerate(row["activities"][:max_activities]):
            base = n_left + i * len(_BLOCK)
            ws.cell(r, base + 1, act["project_code"])
            ws.cell(r, base + 2, act["activity_type"])
            ws.cell(r, base + 3, act["sub_activity_type"])
            ws.cell(r, base + 4, act["tags"])
            ws.cell(r, base + 5, act["docs"])
            ws.cell(r, base + 6, act["bom"])
            ws.cell(r, base + 7, act["spares"])
        ws.cell(r, remarks_col, row["remarks"])
        for col in range(1, total_cols + 1):
            _style_data_cell(ws.cell(r, col), col in centers, col == remarks_col, col == 2)

    # rows are ordered by employee_code → contiguous employee sections.
    employees = [(label, list(grp)) for label, grp in groupby(rows, key=lambda r: r["employee_label"])]

    # Single employee (or none): one top header, no title/spacer rows.
    if len(employees) <= 1:
        _write_header(ws, 1, columns)
        ws.freeze_panes = "A2"
        r = 2
        for _, emp_rows in employees:
            for row in emp_rows:
                write_data_row(r, row)
                r += 1
        return _finalize(wb)

    # Multiple employees: a self-contained section per employee.
    r = 1
    for label, emp_rows in employees:
        _write_group_header(ws, r, total_cols, label)
        r += 1
        _write_header(ws, r, columns)
        r += 1
        for row in emp_rows:
            write_data_row(r, row)
            r += 1
        r += 1  # blank spacer row before the next employee

    return _finalize(wb)
