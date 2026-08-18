"""Read-only check: does the calendar cell now agree with the day popover?

Replays the REAL data behind both surfaces for one month and prints, per day,
what the calendar cell used to show, what it shows after the fix, and what the
popover's status line says. Writes nothing.

    docker exec wms-backend-1 python -m scripts.verify_calendar_status 2026 8
"""
from __future__ import annotations

import sys
from datetime import date

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.attendance.models import AttendanceRecord
from app.modules.biometric.constants import PROVIDER_EASYTIME
from app.modules.biometric.service import list_daily_summary
from app.modules.users.models import User

CLASSIFICATION_LABEL = {
    "present": "Present",
    "incomplete": "Incomplete",
    "needs_review": "Needs review",
    "no_record": "No biometric record",
}


def duration(minutes: int | None) -> str:
    if minutes is None:
        return "-"
    return f"{minutes // 60}h {minutes % 60:02d}m"


def old_cell(record_status: str | None) -> str:
    """What the cell rendered before: the official record, or nothing."""
    return record_status or ""


def new_cell(record_status: str | None, classification: str) -> str:
    """`resolveDayStatus`, restated: record first, then a settled `present`."""
    if record_status:
        return record_status
    return "present" if classification == "present" else ""


def main() -> int:
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2026
    month = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    date_from = date(year, month, 1)
    date_to = date(year + (month == 12), (month % 12) + 1, 1)
    date_to = date.fromordinal(date_to.toordinal() - 1)

    db = SessionLocal()
    try:
        actor = db.scalars(
            select(User).where(User.role.in_(("admin", "manager", "project_manager"))).limit(1)
        ).first()
        if actor is None:
            print("no admin/manager user to act as")
            return 1
        print(f"actor: {actor.email} ({actor.role})")

        items, _schedule = list_daily_summary(
            db,
            actor=actor,
            provider=PROVIDER_EASYTIME,
            employee_id=None,
            date_from=date_from,
            date_to=date_to,
        )
        if not items:
            print(f"no biometric summaries in {date_from} .. {date_to}")
            return 0

        records = {
            (r.employee_id, r.attendance_date): getattr(r.status, "value", r.status)
            for r in db.scalars(
                select(AttendanceRecord).where(
                    AttendanceRecord.attendance_date.between(date_from, date_to)
                )
            )
        }

        header = f"{'employee':<12} {'date':<11} {'class':<13} {'worked':<8} {'record':<9} {'OLD cell':<9} {'NEW cell':<9} popover"
        print(header)
        print("-" * len(header))
        fixed = 0
        for item in sorted(items, key=lambda i: (str(i["employee_code"]), i["summary_date"])):
            status = records.get((item["employee_id"], item["summary_date"]))
            old = old_cell(status)
            new = new_cell(status, item["classification"])
            label = status.replace("_", " ").title() if status else CLASSIFICATION_LABEL[item["classification"]]
            popover = label
            if item["worked_minutes"] is not None:
                popover = f"{label} Â· {duration(item['worked_minutes'])}"
            if old != new:
                fixed += 1
            print(
                f"{str(item['employee_code']):<12} {str(item['summary_date']):<11} "
                f"{item['classification']:<13} {duration(item['worked_minutes']):<8} "
                f"{status or '-':<9} {old or '(blank)':<9} {new or '(blank)':<9} {popover}"
            )
        print(f"\n{len(items)} day rows, {fixed} previously-blank cell(s) now carry a status")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())

