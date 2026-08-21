"""PM Weekly Activity Report — flat row shape shared by preview + Excel export.

One row per Employee + Date, carrying that day's activities as a list. The
preview renders the list stacked in one table row; the Excel export flattens it
to ONE SHEET ROW PER ACTIVITY (half-day). Both derive from this one structure,
so the preview always shows what the export contains."""
from datetime import date

from pydantic import BaseModel


class ActivityCell(BaseModel):
    # Which half of the day this activity belongs to ('first_half' /
    # 'second_half' / 'full_day'; None on legacy rows without a period), and that
    # half's own day status when a split day mixes two. Both are read straight
    # off work_report_periods.
    day_part: str | None = None
    period_status: str | None = None
    project_code: str | None
    activity_type: str | None
    sub_activity_type: str | None
    tags: int
    docs: int
    bom: int
    spares: int
    pages: int
    records: int
    # Benchmark as frozen on the task at submit time: the mode
    # (NUMERIC*/TASK_*), the effective per-period target, and the unit the target
    # is counted in. Rendered by the export ("120 TAGS" / "LS" / "LS - 300
    # SPARES"); never recomputed.
    benchmark_type: str | None = None
    benchmark_value: float | None = None
    benchmark_unit: str | None = None


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
