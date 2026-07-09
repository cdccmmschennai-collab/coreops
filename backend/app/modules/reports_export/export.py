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

_PB_LEFT = [
    ("Emp Code & Name", 26.0),
    ("Date", 12.0),
    ("Project", 24.0),
    ("Activity", 22.0),
    ("Sub Activity", 22.0),
]
_PB_GROUPS = ["Benchmark Target", "Actual Completed", "Pending Benchmark"]
_PB_UNITS = ["tags", "docs", "bom", "spares"]  # ledger benchmark_unit values
_PB_UNIT_LABELS = ["Tags", "Docs", "BOM", "Spares"]
_PB_RIGHT = [("Cycle Start", 12.0), ("Cycle End", 12.0)]


def build_pending_benchmark_workbook(rows: list[dict], cycle_start, cycle_end) -> BytesIO:
    """Pending Benchmark XLSX: employee-wise sections of date-wise pending
    rows, then one bold TOTAL row per employee. Two header rows — flat columns
    span both rows; Benchmark Target / Actual Completed / Pending Benchmark
    each merge across their Tags/Docs/BOM/Spares sub-columns. Each data row's
    numbers land only in the sub-column matching its benchmark unit; the other
    three stay blank (a sub-activity has exactly one counted field). `rows`
    must arrive sorted employee-first (the service guarantees it)."""
    wb, ws = _new_sheet()
    ws.title = PENDING_SHEET_NAME

    n_left = len(_PB_LEFT)
    first_right = n_left + 1 + len(_PB_GROUPS) * 4  # first Cycle column
    total_cols = first_right + len(_PB_RIGHT) - 1
    date_cols = {2, first_right, first_right + 1}

    # Header rows 1-2: flat columns merged vertically, group labels merged
    # across their four sub-columns.
    for idx, (label, width) in enumerate(_PB_LEFT, start=1):
        ws.merge_cells(start_row=1, start_column=idx, end_row=2, end_column=idx)
        ws.cell(1, idx, label)
        ws.column_dimensions[get_column_letter(idx)].width = width
    for gi, group in enumerate(_PB_GROUPS):
        start = n_left + 1 + gi * 4
        ws.merge_cells(start_row=1, start_column=start, end_row=1, end_column=start + 3)
        ws.cell(1, start, group)
        for ui, unit_label in enumerate(_PB_UNIT_LABELS):
            ws.cell(2, start + ui, unit_label)
            ws.column_dimensions[get_column_letter(start + ui)].width = 9.0
    for ri, (label, width) in enumerate(_PB_RIGHT):
        col = first_right + ri
        ws.merge_cells(start_row=1, start_column=col, end_row=2, end_column=col)
        ws.cell(1, col, label)
        ws.column_dimensions[get_column_letter(col)].width = width
    for row in (1, 2):
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = _HEADER_FONT
            cell.fill = _HEADER_FILL
            cell.border = _BORDER
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.freeze_panes = "A3"

    def style_row(r: int, bold: bool = False) -> None:
        for col in range(1, total_cols + 1):
            cell = ws.cell(row=r, column=col)
            _style_data_cell(cell, n_left < col < first_right, False, col in date_cols)
            if bold:
                cell.font = _GROUP_FONT
                cell.fill = _GROUP_FILL

    unit_col = {u: i for i, u in enumerate(_PB_UNITS)}
    r = 3
    for _, emp_rows in groupby(rows, key=lambda x: x["employee_label"]):
        totals = [[0.0] * 4 for _ in _PB_GROUPS]
        used = [False] * 4
        for row in emp_rows:
            ws.cell(r, 1, row["employee_label"])
            ws.cell(r, 2, row["date"])
            ws.cell(r, 3, row["project"])
            ws.cell(r, 4, row["activity"])
            ws.cell(r, 5, row["sub_activity"])
            ui = unit_col.get(row["unit"])
            if ui is not None:
                for gi, key in enumerate(("target", "actual", "pending")):
                    value = float(row[key])
                    ws.cell(r, n_left + 1 + gi * 4 + ui, value)
                    totals[gi][ui] += value
                used[ui] = True
            ws.cell(r, first_right, cycle_start)
            ws.cell(r, first_right + 1, cycle_end)
            style_row(r)
            r += 1

        # TOTAL row: label sits in Sub Activity; sums only for units this
        # employee actually reported (the rest stay blank, like data rows).
        ws.cell(r, 5, "TOTAL")
        for gi in range(len(_PB_GROUPS)):
            for ui in range(4):
                if used[ui]:
                    ws.cell(r, n_left + 1 + gi * 4 + ui, totals[gi][ui])
        style_row(r, bold=True)
        r += 1

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
