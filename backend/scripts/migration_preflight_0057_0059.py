"""READ-ONLY production preflight for migrations 0057, 0058 and 0059.

Captures the exact state the DOCS -> RECORDS conversion depends on, so the
post-migration verifier can prove nothing was lost or double-counted. Writes a
JSON snapshot plus a readable summary.

This script NEVER writes: it opens the connection read-only, runs SELECTs only,
and rolls back. It is safe to run against live production.

    python scripts/migration_preflight_0057_0059.py --out preflight.json
    python scripts/migration_preflight_0057_0059.py --database-url postgresql+psycopg://...

Exit codes
    0  safe to proceed
    1  a gate failed - DO NOT MIGRATE (see the FAILED lines)
    2  could not connect / unexpected error
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, text

# The revision the database must be on BEFORE this batch runs, and the head it
# must reach after. 0057's down_revision is 0056_work_items.
EXPECTED_CURRENT = {"0056_work_items"}
# Re-running the preflight after a partial batch is a legitimate state to
# report, but it is NOT a safe starting point for a fresh run.
PARTIAL = {"0057_reconcile_activity_requests", "0058_pages_records_units"}
EXPECTED_HEAD = "0059_activity_req_pages_records"

PARENT_NAME = "DOC IDB"
# Exact trimmed sub-activity names - no prefix or ILIKE matching. Three other
# DOC IDB sub-activities are genuinely document-based and MUST stay on DOCS.
SUB_NAMES = [
    "DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)",
    (
        "DOC IDB-DOC FILE PATH/POPULATION OF DOC.NO/DWG NO/TITLE/DOC.TYPE AND "
        "ORGANISING DOC.TYPE FOLDER IF MDR/VDR NOT AVAILABLE"
    ),
    "DOC IDB-DOC FILE PATH MIGRATION WITH MDR/VDR AND MANUAL MATCHING",
]


def _json_default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o)}")


def _url(cli_url: str | None) -> str:
    url = cli_url or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: pass --database-url or set DATABASE_URL", file=sys.stderr)
        raise SystemExit(2)
    return url


def collect(conn) -> dict:
    out: dict = {}

    out["captured_at"] = datetime.now().isoformat(timespec="seconds")
    ident = conn.execute(
        text(
            "SELECT current_database() AS db, current_user AS usr, "
            "inet_server_addr()::text AS host, inet_server_port() AS port, "
            "version() AS version"
        )
    ).mappings().one()
    out["database"] = dict(ident)

    out["alembic_current"] = conn.execute(
        text("SELECT version_num FROM alembic_version")
    ).scalar_one_or_none()
    out["alembic_expected_head"] = EXPECTED_HEAD

    out["totals"] = {
        "work_reports": conn.execute(
            text("SELECT count(*) FROM daily_work_reports")
        ).scalar_one(),
        "work_report_tasks": conn.execute(
            text("SELECT count(*) FROM work_report_tasks")
        ).scalar_one(),
        "activity_requests": conn.execute(
            text("SELECT count(*) FROM activity_requests")
        ).scalar_one(),
    }

    # 0057 adds a partial unique index on (employee_id, report_id) WHERE
    # status='pending'. Pre-existing duplicates would make it fail mid-migration.
    dupes = conn.execute(
        text(
            """
            SELECT employee_id::text, report_id::text, count(*) AS n
              FROM activity_requests
             WHERE status = 'pending' AND report_id IS NOT NULL
             GROUP BY employee_id, report_id
            HAVING count(*) > 1
             ORDER BY n DESC
            """
        )
    ).mappings().all()
    out["duplicate_pending_groups"] = [dict(r) for r in dupes]

    # --- the three sub-activities the DOCS -> RECORDS move targets -----------
    # Resolved by EXACT trimmed (parent, sub) name, exactly as migration 0058
    # resolves them: local UUIDs are not production UUIDs.
    targets = []
    for sub_name in SUB_NAMES:
        rows = conn.execute(
            text(
                """
                SELECT s.id::text                AS activity_master_id,
                       btrim(p.name)             AS parent_name,
                       btrim(s.name)             AS sub_activity_name,
                       s.is_active,
                       s.benchmark_type,
                       s.relevant_count_field
                  FROM activity_master s
                  JOIN activity_master p ON p.id = s.parent_id
                 WHERE btrim(p.name) = :parent AND btrim(s.name) = :sub
                 ORDER BY s.is_active DESC, s.id
                """
            ),
            {"parent": PARENT_NAME, "sub": sub_name},
        ).mappings().all()

        for r in rows:
            entry = dict(r)
            stats = conn.execute(
                text(
                    """
                    SELECT count(*)                          AS linked_task_count,
                           coalesce(sum(t.docs_count), 0)    AS docs_total,
                           coalesce(sum(t.records_count), 0) AS records_total,
                           min(w.report_date)                AS min_report_date,
                           max(w.report_date)                AS max_report_date
                      FROM work_report_tasks t
                      JOIN daily_work_reports w ON w.id = t.report_id
                     WHERE t.sub_activity_id = CAST(:sid AS uuid)
                    """
                ),
                {"sid": entry["activity_master_id"]},
            ).mappings().one()
            entry.update(dict(stats))

            snaps = conn.execute(
                text(
                    """
                    SELECT coalesce(t.relevant_count_field_snapshot, '(null)') AS snapshot,
                           count(*) AS n
                      FROM work_report_tasks t
                     WHERE t.sub_activity_id = CAST(:sid AS uuid)
                     GROUP BY 1 ORDER BY 2 DESC
                    """
                ),
                {"sid": entry["activity_master_id"]},
            ).mappings().all()
            entry["snapshot_distribution"] = {r["snapshot"]: r["n"] for r in snaps}

            # Row ids, so the verifier can prove none disappeared.
            entry["task_ids"] = [
                str(x)
                for x in conn.execute(
                    text(
                        "SELECT id FROM work_report_tasks "
                        "WHERE sub_activity_id = CAST(:sid AS uuid) ORDER BY id"
                    ),
                    {"sid": entry["activity_master_id"]},
                ).scalars().all()
            ]
            targets.append(entry)

    out["target_activities"] = targets
    out["resolution"] = {
        name: sum(1 for t in targets if t["sub_activity_name"] == name)
        for name in SUB_NAMES
    }

    # --- unrelated DOCS checksum -------------------------------------------
    # Every DOCS-bearing row NOT belonging to the three targets. The migration
    # must leave these untouched.
    target_ids = [t["activity_master_id"] for t in targets]
    unrelated = conn.execute(
        text(
            """
            SELECT count(*)                       AS row_count,
                   coalesce(sum(t.docs_count), 0) AS docs_total
              FROM work_report_tasks t
             WHERE t.docs_count > 0
               AND (t.sub_activity_id IS NULL
                    OR NOT (t.sub_activity_id::text = ANY(:ids)))
            """
        ),
        {"ids": target_ids or [""]},
    ).mappings().one()
    out["unrelated_docs"] = dict(unrelated)

    return out


def evaluate(snap: dict) -> list[tuple[bool, str]]:
    """Gates. Each is (ok, message); any False means DO NOT MIGRATE."""
    gates: list[tuple[bool, str]] = []

    cur = snap["alembic_current"]
    if cur in EXPECTED_CURRENT:
        gates.append((True, f"alembic revision {cur} is the expected starting point"))
    elif cur in PARTIAL:
        gates.append((False, f"alembic revision {cur} - batch PARTIALLY applied, resolve before rerunning"))
    elif cur == EXPECTED_HEAD:
        gates.append((False, f"alembic revision {cur} - already at head, nothing to migrate"))
    else:
        gates.append((False, f"alembic revision {cur!r} is UNEXPECTED (want one of {sorted(EXPECTED_CURRENT)})"))

    dupes = snap["duplicate_pending_groups"]
    gates.append((
        not dupes,
        f"{len(dupes)} duplicate pending activity-request group(s)"
        + (" - 0057's unique index would fail" if dupes else ""),
    ))

    # Each exact sub-activity must resolve, and must not be ambiguous.
    for name, n in snap["resolution"].items():
        short = name[:48] + ("..." if len(name) > 48 else "")
        if n == 0:
            gates.append((False, f"sub-activity NOT FOUND: {short}"))
        elif n == 1:
            gates.append((True, f"resolved exactly 1 row: {short}"))
        else:
            active = [
                t for t in snap["target_activities"]
                if t["sub_activity_name"] == name and t["is_active"]
            ]
            withdata = [
                t for t in snap["target_activities"]
                if t["sub_activity_name"] == name and t["linked_task_count"] > 0
            ]
            ok = len(active) <= 1 and len(withdata) <= 1
            gates.append((
                ok,
                f"resolved {n} rows ({len(active)} active, {len(withdata)} with history): {short}"
                + ("" if ok else " - AMBIGUOUS, resolution unsafe"),
            ))

    # Historical counts must be internally consistent: a row counted in the
    # snapshot distribution for every linked task.
    for t in snap["target_activities"]:
        dist_total = sum(t["snapshot_distribution"].values())
        ok = dist_total == t["linked_task_count"] == len(t["task_ids"])
        gates.append((
            ok,
            f"{t['sub_activity_name'][:40]}...: {t['linked_task_count']} tasks, "
            f"{dist_total} snapshot rows, {len(t['task_ids'])} ids"
            + ("" if ok else " - INCONSISTENT"),
        ))

    return gates


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--out", default="preflight_0057_0059.json")
    args = ap.parse_args()

    engine = create_engine(_url(args.database_url))
    # Read-only on the server side: any accidental write raises instead of
    # silently succeeding.
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        snap = collect(conn)
        conn.rollback()

    gates = evaluate(snap)
    snap["gates"] = [{"ok": ok, "message": m} for ok, m in gates]
    failed = [m for ok, m in gates if not ok]
    snap["safe_to_migrate"] = not failed

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2, default=_json_default)

    d = snap["database"]
    print("=" * 78)
    print("MIGRATION PREFLIGHT - 0057 / 0058 / 0059   (READ ONLY)")
    print("=" * 78)
    print(f"database        : {d['db']} @ {d['host']}:{d['port']} as {d['usr']}")
    print(f"captured        : {snap['captured_at']}")
    print(f"alembic current : {snap['alembic_current']}")
    print(f"alembic head    : {snap['alembic_expected_head']}")
    print()
    print(f"work_reports      : {snap['totals']['work_reports']}")
    print(f"work_report_tasks : {snap['totals']['work_report_tasks']}")
    print(f"activity_requests : {snap['totals']['activity_requests']}")
    print(f"duplicate pending : {len(snap['duplicate_pending_groups'])}")
    print()
    print("-- DOC IDB targets (exact trimmed match) " + "-" * 37)
    if not snap["target_activities"]:
        print("  (none resolved)")
    for t in snap["target_activities"]:
        print(f"  id            : {t['activity_master_id']}")
        print(f"  parent / sub  : {t['parent_name']} / {t['sub_activity_name']}")
        print(f"  active        : {t['is_active']}   type={t['benchmark_type']} unit={t['relevant_count_field']}")
        print(f"  linked tasks  : {t['linked_task_count']}")
        print(f"  docs total    : {t['docs_total']}")
        print(f"  records total : {t['records_total']}")
        print(f"  snapshots     : {t['snapshot_distribution'] or '{}'}")
        print(f"  report dates  : {t['min_report_date']} .. {t['max_report_date']}")
        print()
    u = snap["unrelated_docs"]
    print(f"-- unrelated DOCS checksum: {u['row_count']} rows, docs_total={u['docs_total']}")
    print()
    print("-- gates " + "-" * 69)
    for ok, m in gates:
        print(f"  [{'PASS' if ok else 'FAIL'}] {m}")
    print()
    print(f"snapshot written: {args.out}")
    print("RESULT:", "SAFE TO MIGRATE" if not failed else "DO NOT MIGRATE")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"PREFLIGHT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
