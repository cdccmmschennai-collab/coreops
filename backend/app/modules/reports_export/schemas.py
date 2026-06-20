"""PM Weekly Activity Report — flat row shape shared by preview + Excel export.

One row per Employee + Date (matching SAMPLE.xlsx). Multiple activities on the
same day fill additional activity column groups within the same row, so the
preview and the export both derive from this single structure."""
from datetime import date

from pydantic import BaseModel


class ActivityCell(BaseModel):
    project_code: str | None
    activity_type: str | None
    sub_activity_type: str | None
    tags: int
    docs: int
    bom: int
    spares: int


class ActivityRow(BaseModel):
    employee_label: str          # "EMP001 - EMP 1" — repeated on every row
    report_date: date
    day_status: str | None
    remarks: str | None
    activities: list[ActivityCell]


class ActivityReportOut(BaseModel):
    # Max activities on any single Employee+Date across the dataset → drives the
    # dynamic activity-column count. >=1 so the sheet is never 0-wide.
    max_activities: int
    rows: list[ActivityRow]
