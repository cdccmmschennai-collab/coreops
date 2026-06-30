"""One-time cleanup: deactivate the attendance/admin Activity Master entries that
have been moved to the work-report **Day Status** dropdown (migration 0048).

These nine activities (and their sub-activities) were originally seeded into the
Activity Master by seed_activity_master.py as pure attendance/admin logging lines.
They now live as Day Status options instead, so they no longer belong in the
Activity / Sub-Activity pickers on the report form.

The Activity / Sub-Activity dropdowns read live from the `activity_master` table
filtered to is_active = true, so flipping these rows to is_active = false removes
them from the pickers. This is a *soft* deactivation — nothing is deleted, so any
historical work_report_tasks that referenced them keep working and the change is
fully reversible (set is_active = true again, or re-run seed_activity_master.py
after restoring the blocks).

Deactivates the parent activity AND every sub-activity under it.

Usage (from backend/ directory inside the container):
  python scripts/deactivate_attendance_activities.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.activity_master.models import ActivityMaster, LEVEL_ACTIVITY

# Activity names moved to the Day Status dropdown — match seed_activity_master.py.
ATTENDANCE_ACTIVITY_NAMES = [
    "LEAVE",
    "COMPANY HOLIDAY",
    "WORK FROM HOME",
    "WEEK OFF",
    "WORK AT OFFICE",
    "COMP-OFF",
    "OVERTIME HOURS-COMPENSATION",
    "OVERTIME HOURS-SALARY",
    "PERMISSION",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as db:
        activities = (
            db.query(ActivityMaster)
            .filter(
                ActivityMaster.level == LEVEL_ACTIVITY,
                ActivityMaster.name.in_(ATTENDANCE_ACTIVITY_NAMES),
            )
            .all()
        )

        to_change: list[ActivityMaster] = []
        for activity in activities:
            children = (
                db.query(ActivityMaster)
                .filter(ActivityMaster.parent_id == activity.id)
                .all()
            )
            for row in [activity, *children]:
                if row.is_active:
                    to_change.append(row)

        found = {a.name for a in activities}
        missing = [n for n in ATTENDANCE_ACTIVITY_NAMES if n not in found]
        if missing:
            print(f"Note: not present in Activity Master (skipped): {', '.join(missing)}")

        if args.dry_run:
            print(f"DRY RUN — would deactivate {len(to_change)} row(s):")
            for row in to_change:
                kind = "activity" if row.level == LEVEL_ACTIVITY else "  sub"
                print(f"  [{kind}] {row.name}")
            return

        for row in to_change:
            row.is_active = False
            db.add(row)
        db.commit()
        print(f"Done: deactivated {len(to_change)} Activity Master row(s).")


if __name__ == "__main__":
    main()
