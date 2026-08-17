"""Builds the per-PM CSV attachment for the daily report reminder.

Responsibility (only): turn the presentational rows into CSV bytes Excel opens
cleanly. No SMTP, no queries, no business rules.

Only one date is ever reported on (the previous working day), so every row
carries the same single "Missing Report Date" and there is no multi-date cell.
Employee ID and name stay in separate columns so the sheet stays filterable.

Excel specifics:
  * UTF-8 **with BOM** - without it Excel decodes the file as the local ANSI code
    page and mangles any non-ASCII employee names.
  * CRLF line endings, which is what ``csv.writer`` emits with ``lineterminator``
    set explicitly (the default already is CRLF, but pinning it keeps the file
    stable regardless of how the caller opened the stream).
"""
from __future__ import annotations

import csv
import io
from datetime import date

CSV_COLUMNS = [
    "Employee ID",
    "Employee Name",
    "Missing Report Date",
]

_UTF8_BOM = b"\xef\xbb\xbf"


def csv_filename(for_date: date) -> str:
    """``coreops_outstanding_reports_2026-08-12.csv`` (the target date)."""
    return f"coreops_outstanding_reports_{for_date.isoformat()}.csv"


def build_csv(
    rows: list[tuple[str, str]], *, report_date: date, date_fmt: str
) -> bytes:
    """Render ``(code, name)`` rows as Excel-ready CSV bytes for ``report_date``.

    ``rows`` is the same list the HTML/text tables are built from, so the CSV can
    never disagree with the email body or leak another PM's employees.
    """
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(CSV_COLUMNS)
    date_label = report_date.strftime(date_fmt)
    for code, name in rows:
        writer.writerow([code, name, date_label])
    return _UTF8_BOM + buffer.getvalue().encode("utf-8")
