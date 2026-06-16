"""Seed Planning Plant / Maintenance Plant master data (SAP reference codes).

Source: the company's SAP plant master list (Planning Plant + Maintenance
Plant sheets), supplied directly by the PM. Embedded as a literal dataset —
static reference data, not re-parsed from a spreadsheet each run.

Idempotent: upserts by code. Safe to re-run.

Usage (from backend/ directory inside the container):
  python scripts/seed_plants.py [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.modules.plants.models import MaintenancePlant, PlanningPlant

PLANNING_PLANTS = [
    ("1200", "Qatar Petroleum - Doha"),
    ("2300", "Dukhan Planning Plant"),
    ("2400", "Messaieed Planning Plant"),
    ("2500", "Refinery Planning Plant"),
    ("2600", "Offshore Planning Plant"),
    ("2700", "Ras Laffan Planning Plant"),
    ("2800", "Mesaieed Industrial City"),
    ("2900", "North Field Alpha"),
    ("3000", "Ras Laffan Common Cooling Water"),
]

# (code, description, planning_plant_code)
MAINTENANCE_PLANTS = [
    ("ARBC", 'Arab "C"', "2600"),
    ("ARBD", 'Arab "D"', "2300"),
    ("BRT6", "Berth 6 Rfnry Export Import", "2500"),
    ("CLS1", "PWI Cluster 1 Dukhan", "2300"),
    ("CLS2", "PWI Cluster 2 Dukhan", "2300"),
    ("CLS3", "PWI Cluster 3 Dukhan", "2300"),
    ("CSMD", "COMMUNITY SERVICES", "2300"),
    ("DCPS", "Dukhan Cathodic Prtctn Satns", "2300"),
    ("DKDP", "Dukhan Water Storage & Dist", "2300"),
    ("DKDSP", None, "2300"),
    ("DKFL", "Dukhan - Field Support Logistics", "2300"),
    ("DKPS", "Dukhan Power Plant", "2300"),
    ("DKPW", "Power Dist Dukhan", "2300"),
    ("DKSP", "Dukhan Sewage Plant", "2300"),
    ("DKSS", "Dukhan Support Services", "2300"),
    ("DYAB", "DIYAB", "2300"),
    ("FAHM", "Fahahil Main", "2300"),
    ("FAHN", "Fahahil North", "2300"),
    ("FAHS", "Fahahil South", "2300"),
    ("FHGL", "Fahahil North Gas Lift Comp", "2300"),
    ("FHNF", "Fahahil North Field", "2300"),
    ("FHSP", "Fahahil Stripping Plant", "2300"),
    ("GDSP", "Gas Flowlines - Dukhan", "2300"),
    ("GSMD", "GENERAL SERVICES", "1200"),
    ("GSU1", None, "2300"),
    ("HLUL", "Halul  Island", "2600"),
    ("JALM", "Jaleha Main", "2300"),
    ("KAHM", "Khatiyah Main", "2300"),
    ("KAHN", "Khatiyah North", "2300"),
    ("KAHS", "Khatiyah South", "2300"),
    ("KSFSS", None, "2300"),
    ("KUFA", "Khuff Gas Station A", "2300"),
    ("KUFB", "Khuff Gas Station B", "2300"),
    ("KUFC", "Khuff Gas Station C", "2300"),
    ("KUFD", "Khuff Gas Station D", "2300"),
    ("KUFE", "Khuff Gas Station E", "2300"),
    ("KUFG", "Khuff Gas Station G", "2300"),
    ("KUFH", "Khuff Gas Station H", "2300"),
    ("KUFL", "Khuff Gas Stations L", "2300"),
    ("LBVS", "Dukhan Line Break Valve Statns", "2300"),
    ("MHWC", "MIC WASTE MANAGEMENT", "2800"),
    ("MICM", "MIC INFRASTRUCTURE", "2800"),
    ("MICS", "Mesaieed Industrial City", "2800"),
    ("MPRT", "Mesaieed Port", "2800"),
    ("MROP", "Marine Operations", "2600"),
    ("MSTP", "MIC INFRASTRUCTURE", "2800"),
    ("NFAO", "North Field Alpha", "2900"),
    ("NGCF", "Mesaieed Common Facilities", "2400"),
    ("NGCU", "Mesaieed Common Utilities", "2400"),
    ("NGDS", "NGL Gas Distribution Stations", "2400"),
    ("NGL1", "NGL1 Mesaieed", "2400"),
    ("NGL2", "NGL2 Mesaieed", "2400"),
    ("NGL3", "NGL3 Mesaieed", "2400"),
    ("NGL4", "NGL4 Mesaieed", "2400"),
    ("NGSF", "NGL  Gas Sweetening  Facility", "2400"),
    ("NGSL", "NGL  Storage & Loading", "2400"),
    ("NGTT", "Oil Tank Farm & Terminal", "2400"),
    ("ODSP", "Oil Flowlines - Dukhan", "2300"),
    ("OESS", "OPERATION ENGINEERING SUPPORT SYSTEM", "2300"),
    ("OFST", "Offsite Tank Frm & Gnrl Bldngs", "2500"),
    ("OSCW", "OSER Cooling Water Facility", "2700"),
    ("OSDK", "OSER Dukhan", "2700"),
    ("OSDO", "OSER Doha", "2700"),
    ("OSHL", "OSER Halul", "2700"),
    ("OSMI", "OSER Meassaieed Indus City", "2700"),
    ("OSMR", "OSER Refinery", "2700"),
    ("OSRL", "OSER Ras Laffan Indus City", "2700"),
    ("PNTN", "Khuff Point N", "2300"),
    ("PNTU", "Khuff Point U", "2300"),
    ("PS02", "PS2 Maydan Mahzam", "2600"),
    ("PS03", "PS3 Bul Hanine", "2600"),
    ("PW01", "Powered Water Inj Station 1", "2300"),
    ("PW02", "Powered Water Inj Station 2", "2300"),
    ("PW03", "Powered Water Inj Station 3", "2300"),
    ("PW04", "Powered Water Inj Station 4", "2300"),
    ("PW05", "Powered Water Inj Station 5", "2300"),
    ("PW06", "Powered Water Inj Station 6", "2300"),
    ("PW07", "Powered Water Inj Station 7", "2300"),
    ("PW08", "Powered Water Inj Station 8", "2300"),
    ("PW09", "Powered Water Inj Station 9", "2300"),
    ("PWRM", "Power Water Injecn Ring Main", "2300"),
    ("QATX", "AQP- Caltex Joint Venture Co", "2500"),
    ("QPSFA", "CHEMICAL STORES", "2300"),
    ("RAC1", "Ras Laffan Accom Camp 1", "2700"),
    ("RAC2", "Ras Laffan Accom Camp 2", "2700"),
    ("RCON", "Condensate Refinery", "2500"),
    ("RCSF", "Ras Laffan Common Seawater Fac", "3000"),
    ("REF1", "Refinery 1", "2500"),
    ("REF2", "Refinery 2", "2500"),
    ("RFCC", "Refinery Fluid Catalytic Conve", "2500"),
    ("RFLS", "Refinery Facilities", "2500"),
    ("RLAB", "Refinery Linear Alkyl Benzene", "2500"),
    ("RLIN", "Ras Laffan Infrastructure", "2700"),
    ("RLIW", "RAS LAFFAN INFRASTRUCTURE WEST", "2700"),
    ("RLPG", "LPG Bottling Plants No.1 & 2", "2500"),
    ("RPRT", "Ras Laffan Port", "2700"),
    ("RUTL", "Refinery Utilities", "2500"),
    ("RWTP", "RAS LAFFAN WASTEWATER TREATMENT PLANTS", "2700"),
    ("UMBA", "Umm Bab Oil Pumping Station", "2300"),
    ("UMBB", "Umm Bab Oil Pumping Station", "2300"),
    ("UMBC", "Umm Bab Oil Pumping Station", "2300"),
    ("VSSL", "Offshore Vessels/WorkBoats", "2600"),
    ("WQOD", "Qatar Fuel Co WOQOD Doha Depot", "2500"),
    ("WSHP", "Marine Dept Workshops", "2600"),
]


def _upsert_planning_plants(db) -> dict:
    """Returns {planning_plant_code: id}."""
    code_to_id = {}
    for code, description in PLANNING_PLANTS:
        existing = db.query(PlanningPlant).filter(PlanningPlant.code == code).one_or_none()
        if existing is None:
            row = PlanningPlant(code=code, description=description)
            db.add(row)
            db.flush()
            code_to_id[code] = row.id
        else:
            if existing.description != description:
                existing.description = description
                db.add(existing)
            code_to_id[code] = existing.id
    return code_to_id


def _upsert_maintenance_plants(db, planning_plant_ids: dict) -> int:
    changed = 0
    for code, description, pp_code in MAINTENANCE_PLANTS:
        pp_id = planning_plant_ids[pp_code]
        existing = db.query(MaintenancePlant).filter(MaintenancePlant.code == code).one_or_none()
        if existing is None:
            db.add(MaintenancePlant(code=code, description=description, planning_plant_id=pp_id))
            changed += 1
            continue
        if existing.description != description or existing.planning_plant_id != pp_id:
            existing.description = description
            existing.planning_plant_id = pp_id
            db.add(existing)
            changed += 1
    return changed


def main():
    parser = argparse.ArgumentParser(description="Seed Planning/Maintenance Plant master data.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        print(f"DRY RUN — would upsert {len(PLANNING_PLANTS)} planning plants, "
              f"{len(MAINTENANCE_PLANTS)} maintenance plants.")
        return

    with SessionLocal() as db:
        planning_plant_ids = _upsert_planning_plants(db)
        db.flush()
        mp_changed = _upsert_maintenance_plants(db, planning_plant_ids)
        db.commit()

    print(f"Done: {len(PLANNING_PLANTS)} planning plants processed, "
          f"{mp_changed} maintenance plants inserted/updated.")


if __name__ == "__main__":
    main()
