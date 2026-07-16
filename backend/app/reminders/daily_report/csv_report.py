"""Builds the per-PM CSV attachment for the daily report reminder.

Responsibility (only): turn the presentational rows into CSV bytes Excel opens
cleanly. No SMTP, no queries, no business rules.

Excel specifics:
  * UTF-8 **with BOM** - without it Excel decodes the file as the local ANSI code
    page and mangles the bullet separator and any non-ASCII employee names.
  * CRLF line endings, which is what ``csv.writer`` emits with ``lineterminator``
    set explicitly (the default already is CRLF, but pinning it keeps the file
    stable regardless of how the caller opened the stream).
  * All missing dates for an employee stay in a single cell; the csv module
    quotes the cell because the dates are comma-separated.
"""
from __future__ import annotations

import csv
import io
from datetime import date

CSV_COLUMNS = [
    "Employee ID",
    "Employee Name",
    "Missing Days",
    "Missing Report Dates",
]

_CSV_DATE_SEP = ", "
_UTF8_BOM = b"\xef\xbb\xbf"


def csv_filename(for_date: date) -> str:
    """``coreops_outstanding_reports_2026-07-09.csv``."""
    return f"coreops_outstanding_reports_{for_date.isoformat()}.csv"


def build_csv(rows: list[tuple[str, str, int, list[date]]], *, date_fmt: str) -> bytes:
    """Render ``(code, name, missing_days, dates)`` rows as Excel-ready CSV bytes.

    ``rows`` is the same list the HTML/text tables are built from, so the CSV can
    never disagree with the email body or leak another PM's employees.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    for code, name, missing_days, dates in rows:
        writer.writerow(
            [
                code,
                name,
                missing_days,
                _CSV_DATE_SEP.join(d.strftime(date_fmt) for d in dates),
            ]
        )
    return _UTF8_BOM + buffer.getvalue().encode("utf-8")
