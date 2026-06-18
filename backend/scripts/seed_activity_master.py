"""Seed the Activity Master (Activity -> Sub-Activity, with benchmarks) from the
company's ATTN-PLANT-ACTIVITY-SUB ACTIVITY-20260615.xlsx workbook.

Unlike seed_master_data.py (which parses a clean two-column sheet live), this
source sheet needed one-time manual cleanup (a few rows mix a 'LS' marker with a
numeric hint buried in free-text REMARKS; a couple of rows have stray text /
inconsistent SL.NO). The cleaned dataset is embedded below as a literal list
rather than re-parsed from the .xlsx at seed time.

Classification rules applied while cleaning:
  - TAG COUNT is a number      -> benchmark_type='NUMERIC', benchmark_value=<n>
  - TAG COUNT == 'LS'          -> benchmark_type='TASK_BASED' (no quantity target;
                                   must complete within the allocated duration)
  - TAG COUNT blank, but the activity is a real piece of work rather than a pure
    attendance/admin entry (Project Meetings, Familiarization/Training rows,
    Criticality Analysis, Tool Developer, audit/QC-style rows with a duration in
    REMARKS but no count) -> also benchmark_type='TASK_BASED'
  - TAG COUNT blank AND it's a pure attendance/admin entry (Leave, Company
    Holiday, Work From Home, Week Off, Work At Office, Comp-Off, Overtime,
    Permission) or a genuinely untracked line item -> benchmark_type=None (no
    benchmark at all, pure logging)
  - REMARKS is always preserved verbatim in benchmark_remarks regardless of type,
    for admin reference; benchmark_period_days/benchmark_unit_note are a best-
    effort parse of REMARKS (e.g. '1DAY'->1, '2DAYS'->2, '...PAGES/DAY'->PAGES).

relevant_count_field is a UI hint only (never enforced) — set for the four
activities the business explicitly called out (FMTL/MTL -> tags, DOC IDB -> docs,
BOM IDB -> spares); left None elsewhere for the admin to set later if useful.

Idempotent: upserts by (activity name, sub-activity name). Safe to re-run.

Usage (from backend/ directory inside the container):
  python scripts/seed_activity_master.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.activity_master.models import ActivityMaster, LEVEL_ACTIVITY, LEVEL_SUB_ACTIVITY

NUMERIC = "NUMERIC"
TASK_BASED = "TASK_BASED"


def sub(name, type=None, value=None, period=None, unit=None, remarks=None, count_field=None):
    return {
        "name": name,
        "benchmark_type": type,
        "benchmark_value": value,
        "benchmark_period_days": period,
        "benchmark_unit_note": unit,
        "benchmark_remarks": remarks,
        "relevant_count_field": count_field,
    }


# ── source dataset (ATTN-PLANT-ACTIVITY-SUB ACTIVITY-20260615.xlsx, sheet ACTIVITY) ──

ACTIVITIES = [
    {"name": "LEAVE", "subs": [sub("LEAVE")]},
    {"name": "COMPANY HOLIDAY", "subs": [sub("COMPANY HOLIDAY")]},
    {"name": "WORK FROM HOME", "subs": [sub("WORK FROM HOME")]},
    {"name": "WEEK OFF", "subs": [sub("WEEK OFF")]},
    {"name": "WORK AT OFFICE", "subs": [sub("WORK AT OFFICE")]},
    {"name": "COMP-OFF", "subs": [sub("COMP-OFF")]},
    {"name": "OVERTIME HOURS-COMPENSATION", "subs": [sub("OVERTIME HOURS-COMPENSATION")]},
    {"name": "OVERTIME HOURS-SALARY", "subs": [sub("OVERTIME HOURS-SALARY")]},
    {"name": "PERMISSION", "subs": [
        sub("PERMISSION-FIRST HALF 1HR"),
        sub("PERMISSION-SECOND HALF 1HR"),
        sub("PERMISSION-FIRST HALF 2HR"),
        sub("PERMISSION-SECOND HALF 2HR"),
    ]},
    {"name": "PROJECT MEETING", "subs": [
        sub("PROJECT MEETING-FMTL", TASK_BASED),
        sub("PROJECT MEETING-MTL", TASK_BASED),
        sub("PROJECT MEETING-DOC", TASK_BASED),
        sub("PROJECT MEETING-BOM", TASK_BASED),
        sub("PROJECT MEETING-HIEARCHY", TASK_BASED),
        sub("PROJECT MEETING-FLOC/EQPT-IDB(PMEQM)", TASK_BASED),
        sub("PROJECT MEETING-INITIAL IDB", TASK_BASED),
        sub("PROJECT MEETING-WEEKLY/BIWEEKLY", TASK_BASED),
    ]},
    {"name": "TAG ESTIMATION", "subs": [
        sub("TAG ESTIMATION-FAMILIARIZATION", TASK_BASED),
        sub("TAG ESTIMATION-DATA POPULATION"),
        sub("TAG ESTIMATION-REWORK"),
        sub("TAG ESTIMATION-QC"),
    ]},
    {"name": "DEMOLITION", "subs": [
        # No explicit count-field example given for this activity; defaulted to
        # "tags" (tag-removal work) — adjust in Settings -> Activity Master if wrong.
        sub("DEMOLITION-DATA POPULATION", NUMERIC, 150, 1, remarks="1DAY", count_field="tags"),
        sub("DEMOLITION-REWORK", NUMERIC, 250, 1, remarks="1DAY", count_field="tags"),
        sub("DEMOLITION-QC", NUMERIC, 500, 1, remarks="1DAY", count_field="tags"),
        sub("DEMOLITION-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("DEMOLITION-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "FMTL", "subs": [
        sub("FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT AND SPIR DOC.NO/SPIR TAG NO & TNR TAG NUMBER",
            NUMERIC, 100, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL DATA POPULATION-FROM REFERENCE DOC.P&ID /SLD &LAYOUT",
            NUMERIC, 120, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO", NUMERIC, 400, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL DATA POPULATION- TNR TAG NUMBER", NUMERIC, 400, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("FMTL-REWORK", NUMERIC, 250, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL-QC", NUMERIC, 500, 1, remarks="1DAY", count_field="tags"),
        sub("FMTL-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("FMTL-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("FMTL-PUNCH LIST PREPRATION & SUBMISSION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "MTL", "subs": [
        sub("MTL-ASSET PHOTO MERGING", NUMERIC, 160, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-ASSET PHOTO DATA POPULATION", NUMERIC, 100, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-ASSET PHOTO MERGING&DATA POPULATION", NUMERIC, 65, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-DOC.SPIR DATA MIGRATION AFTER BOM", TASK_BASED, period=1, remarks="1DAY"),
        sub("MTL-DOC.DATASHEET DATA POPULATION", NUMERIC, 120, 1, remarks="1DAY", count_field="docs"),
        sub("MTL-DOC.TEST CERTIFCATE DATA POPULATION", NUMERIC, 250, 1, remarks="1DAY", count_field="docs"),
        # Data-quality note: source TAG COUNT='LS' but REMARKS implies 500 pages/day.
        # TAG COUNT is authoritative per the approved import rule -> TASK_BASED.
        sub("MTL-DOC.O&M MANNUALS DATA POPULATION", TASK_BASED, period=1, unit="PAGES",
            remarks="500 REQUIRED PAGES/DAY", count_field="docs"),
        sub("MTL-DOC.CROSS SECTION DATA POPULATION(VALVE SCHEDULE DATA MIGRATION OF  SIZE & MESC CODE)",
            NUMERIC, 250, 1, remarks="1DAY", count_field="docs"),
        sub("MTL-DOC.MATERIAL SUBMITTAL DATA POPULATION", TASK_BASED, period=1, unit="PAGES",
            remarks="500 REQUIRED PAGES/DAY", count_field="docs"),
        sub("MTL-DOC.MRIR/RFI/EPIC DATA POPULATION", TASK_BASED, period=1, unit="PAGES",
            remarks="40 REQUIRED PAGES/DAY", count_field="docs"),
        sub("MTL-LOGICAL APPROCH-EQPT TYPE &SIZE  FROM UNIQUE SPIR AND UPADTE MAKE",
            NUMERIC, 2000, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-E-NAME PLATE CREATION & MERGING WITH ASSET PHOTOGRAPHY",
            NUMERIC, 250, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("MTL-REWORK", NUMERIC, 200, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-QC", NUMERIC, 500, 1, remarks="1DAY", count_field="tags"),
        sub("MTL-PUNCH LIST PREPRATION", TASK_BASED, period=1, remarks="1DAY"),
        sub("MTL-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("MTL-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "HIERARCHY", "subs": [
        # No explicit count-field example given for this activity; defaulted to
        # "tags" (tag-hierarchy work) — adjust in Settings -> Activity Master if wrong.
        sub("HIERARCHY DATA POPULATION TPLNR/TPLMA/POSNR/MSGRP", NUMERIC, 150, 1, remarks="1DAY", count_field="tags"),
        sub("HIERARCHY DATA POPULATION ARBPL/BEBER/STORT", NUMERIC, 250, 1, remarks="1DAY", count_field="tags"),
        sub("HIERARCHY DATA POPULATION MIGRATION OF FMTL DATA", TASK_BASED, period=1, remarks="1DAY"),
        sub("HIERARCHY DATA POPULATION MIGRATION OF MTL DATA", TASK_BASED, period=1, remarks="1DAY"),
        sub("HIERARCHY DATA POPULATION DEFAULT VALUE FROM ALL RECORDS", TASK_BASED, period=1, remarks="1DAY"),
        sub("HIERARCHY DATA POPULATION FIT TO 9LEVEL", NUMERIC, 2000, 1, remarks="1DAY", count_field="tags"),
        sub("HIERARCHY-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("HIERARCHY-REWORK", NUMERIC, 150, count_field="tags"),
        sub("HIERARCHY-QC", NUMERIC, 250, count_field="tags"),
        sub("HIERARCHY-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("HIERARCHY-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "FLOC/EQPT-IDB(PMEQM)", "subs": [
        # No explicit count-field example given for this activity; defaulted to
        # "tags" (equipment/tag work) — adjust in Settings -> Activity Master if wrong.
        sub("HIERARCHY DATA POPULATION MIGRATION OF FMTL/MTL DATA", TASK_BASED, period=1, remarks="1DAY"),
        sub("FLOC/EQPT-IDB(PMEQM)-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("FLOC/EQPT-IDB(PMEQM)-REWORK", NUMERIC, 300, 1, remarks="1DAY", count_field="tags"),
        sub("FLOC/EQPT-IDB(PMEQM)-QC", NUMERIC, 500, 1, remarks="1DAY", count_field="tags"),
        sub("FLOC/EQPT-IDB(PMEQM)-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("FLOC/EQPT-IDB(PMEQM)-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "DOC IDB", "subs": [
        sub("DOC IDB-MDR/VDR CONSOLIDATION (MULTIPLE FILES TO SINGLE FILE)", TASK_BASED, period=1, remarks="1DAY"),
        sub("DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)",
            NUMERIC, 1000, 1, unit="RECORDS", remarks="RECORDS 1DAY", count_field="docs"),
        sub("DOC IDB-DOC FILE PATH/POPULATION OF DOC.NO/DWG NO/TITLE/DOC.TYPE AND ORGANISING DOC.TYPE FOLDER IF MDR/VDR NOT AVAILABLE",
            NUMERIC, 250, 1, unit="RECORDS", remarks="RECORDS 1DAY", count_field="docs"),
        sub("DOC IDB-DOC FILE PATH MIGRATION WITH MDR/VDR AND MANUAL MATCHING",
            NUMERIC, 400, 1, unit="RECORDS", remarks="RECORDS 1DAY", count_field="docs"),
        sub("DOC IDB-DOC MATRIX WITH FMTL DATA MIGRATION&POPULATION", TASK_BASED, period=1, remarks="1DAY"),
        sub("DOC IDB-TYPE WISE DOC.COLLECTION/SPLITUP AND NAMING/ORGANISING FILES DATA AND POULATION AS PER XL WORKING TEMPLATE",
            NUMERIC, 250, 1, remarks="1DAY", count_field="docs"),
        sub("DOC IDB-RENAMING THE SPLITUP DOCUMENT AS PER DOC.BANDING NUMBER AND ORGANISING FILES",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("DOC IDB-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("DOC IDB-REWORK", NUMERIC, 500, 1, remarks="1DAY", count_field="docs"),
        sub("DOC IDB-QC", NUMERIC, 500, 1, remarks="1DAY", count_field="docs"),
        sub("DOC IDB-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("DOC IDB-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "BOM IDB", "subs": [
        sub("BOM IDB-ADDRRESSING SPIR DOC AS PER MDR/PUNCH LIST FOR NOT AVAILABLE SPIR",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("BOM IDB-EXICUTING SPIR TOOL FOR OUT PUT FILE", TASK_BASED, period=1, remarks="1DAY"),
        sub("BOM IDB-ADDRESSING TAG AGAINST SPIR REQUIRED DOC(LIKE:LCS/INITIAL/NORMAL)",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("BOM IDB-DATA POULATION(MAT.DESC/ASSIGNING DUMMY MAT.NN/MAT.GROUP/MAT.TYPE/TAG AGAINST SUBMT NUMBER)",
            NUMERIC, 100, 1, unit="SPARES", remarks="100SPARES/DAY", count_field="spares"),
        sub("BOM IDB-AUDIT QUERY WITH REPORT", TASK_BASED, period=2, remarks="2DAYS"),
        sub("BOM IDB-REWORK", NUMERIC, 300, 1, unit="SPARES", remarks="300SPARES/DAY", count_field="spares"),
        sub("BOM IDB-QC", NUMERIC, 500, 1, unit="SPARES", remarks="500SPARES/DAY", count_field="spares"),
        sub("BOM IDB-CRS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
        sub("BOM IDB-OVS CORRECTION", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "PM IDB", "subs": [
        # No explicit count-field example given for this activity; defaulted to
        # "tags" (PM-tag work) — adjust in Settings -> Activity Master if wrong.
        sub("PM IDB-ADDRESSING PM REQUIRED TAG", TASK_BASED, period=1, remarks="1DAY"),
        sub("PM IDB-ADDRESSING MAITENANCE TYPE PM/IM/SD/CM AND ISOLATION REQUIRED TAG",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("PM IDB-ADDRESSING EQUIPMENT TYPE WISE MAKE & MODEL AGAINEST EXITING SAP PM DATA",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("PM IDB-ADDRESSING FIRE & GAS PM PLAN EITHER ZONE BASED OR OBJECT TYPE BASED",
            TASK_BASED, period=1, remarks="1DAY"),
        sub("PM IDB-DATA POPULATION", NUMERIC, 40, 1, remarks="1DAY", count_field="tags"),
        sub("PM IDB-AUDIT QUERY WITH REPORT", TASK_BASED, period=1, remarks="1DAY"),
        sub("PM IDB-REWORK", NUMERIC, 100, 1, remarks="1DAY", count_field="tags"),
        sub("PM IDB-QC", TASK_BASED, period=1, remarks="1DAY"),
    ]},
    {"name": "INITIAL IDB", "subs": [
        sub("INITIAL IDB-AUDIT QUERY WITH REPORT", TASK_BASED, period=2, remarks="2DAYS"),
        sub("INITIAL IDB-REWORK", TASK_BASED, period=2, remarks="2DAYS"),
    ]},
    {"name": "FINAL IDB", "subs": [
        sub("FINAL IDB-AUDIT QUERY WITH REPORT", TASK_BASED, period=2, remarks="2DAYS"),
        sub("FINAL IDB-REWORK", TASK_BASED, period=2, remarks="2DAYS"),
    ]},
    {"name": "TRAINING", "subs": [
        sub("MASTERS & REFERENCE FAMILIARIZATION", TASK_BASED),
        sub("DOCUMENT FAMILIARIZATION", TASK_BASED),
        sub("TAG ESTIMATION-FAMILIARIZATION", TASK_BASED),
        sub("FMTL-FAMILIARIZATION", TASK_BASED),
        sub("MTL-FAMILIARIZATION", TASK_BASED),
        sub("BOM-FAMILIARIZATION", TASK_BASED),
        sub("DOC IDB-FAMILIARIZATION", TASK_BASED),
        sub("HIERARCHY-FAMILIARIZATION", TASK_BASED),
        sub("PM-FAMILIARIZATION", TASK_BASED),
        sub("INITIAL IDB-FAMILIARIZATION", TASK_BASED),
        sub("FINAL IDB-FAMILIARIZATION", TASK_BASED),
        sub("CRITICALITY-FAMILIARIZATION", TASK_BASED),
    ]},
    {"name": "TRAINER", "subs": [
        sub("MASTERS & REFERENCE FAMILIARIZATION", TASK_BASED),
        sub("DOCUMENT FAMILIARIZATION", TASK_BASED),
        sub("TAG ESTIMATION-FAMILIARIZATION", TASK_BASED),
        sub("FMTL-FAMILIARIZATION", TASK_BASED),
        sub("MTL-FAMILIARIZATION", TASK_BASED),
        sub("BOM-FAMILIARIZATION", TASK_BASED),
        sub("DOC IDB-FAMILIARIZATION", TASK_BASED),
        sub("HIERARCHY-FAMILIARIZATION", TASK_BASED),
        sub("PM-FAMILIARIZATION", TASK_BASED),
        sub("INITIAL IDB-FAMILIARIZATION", TASK_BASED),
        sub("FINAL IDB-FAMILIARIZATION", TASK_BASED),
        sub("CRITICALITY-FAMILIARIZATION", TASK_BASED),
    ]},
    {"name": "CRITICALITY ANALYSIS", "subs": [
        sub("CRITICALITY ANALYSIS", TASK_BASED),
        sub("CRITICALITY ANALYSIS-AUDIT QUERY WITH REPORT", TASK_BASED),
        sub("CRITICALITY ANALYSIS-QC", TASK_BASED),
    ]},
    {"name": "TOOL DEVELOPER", "subs": [
        sub("SPIR EXTRACTION", TASK_BASED),
        sub("PRODUCTION REPORT TOOL", TASK_BASED),
    ]},
]


# ── upsert ───────────────────────────────────────────────────────────────────

def _upsert_activity(db, name: str, sort_order: int) -> ActivityMaster:
    existing = db.query(ActivityMaster).filter(
        ActivityMaster.level == LEVEL_ACTIVITY, ActivityMaster.name == name,
    ).one_or_none()
    if existing is not None:
        return existing
    row = ActivityMaster(parent_id=None, level=LEVEL_ACTIVITY, name=name, sort_order=sort_order)
    db.add(row)
    db.flush()
    return row


def _upsert_sub_activity(db, activity_id, rec: dict, sort_order: int) -> bool:
    """Returns True if a row was inserted or changed."""
    existing = db.query(ActivityMaster).filter(
        ActivityMaster.level == LEVEL_SUB_ACTIVITY,
        ActivityMaster.parent_id == activity_id,
        ActivityMaster.name == rec["name"],
    ).one_or_none()

    if existing is None:
        db.add(ActivityMaster(
            parent_id=activity_id,
            level=LEVEL_SUB_ACTIVITY,
            name=rec["name"],
            benchmark_type=rec["benchmark_type"],
            benchmark_value=rec["benchmark_value"],
            benchmark_period_days=rec["benchmark_period_days"],
            benchmark_unit_note=rec["benchmark_unit_note"],
            benchmark_remarks=rec["benchmark_remarks"],
            relevant_count_field=rec["relevant_count_field"],
            sort_order=sort_order,
        ))
        return True

    changed = False
    for field in (
        "benchmark_type", "benchmark_value", "benchmark_period_days",
        "benchmark_unit_note", "benchmark_remarks", "relevant_count_field",
    ):
        if getattr(existing, field) != rec[field]:
            setattr(existing, field, rec[field])
            changed = True
    if changed:
        db.add(existing)
    return changed


def main():
    parser = argparse.ArgumentParser(description="Seed the Activity Master from the cleaned dataset.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    total_subs = sum(len(a["subs"]) for a in ACTIVITIES)
    if args.dry_run:
        print(f"DRY RUN — would upsert {len(ACTIVITIES)} activities, {total_subs} sub-activities.")
        return

    with SessionLocal() as db:
        activity_count = 0
        sub_count = 0
        for i, activity in enumerate(ACTIVITIES):
            row = _upsert_activity(db, activity["name"], i)
            activity_count += 1
            for j, rec in enumerate(activity["subs"]):
                if _upsert_sub_activity(db, row.id, rec, j):
                    sub_count += 1
        db.commit()

    print(f"Done: {activity_count} activities processed, {sub_count} sub-activities inserted/updated.")


if __name__ == "__main__":
    main()
