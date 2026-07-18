"""READ-ONLY production preflight for migrations 0057, 0058 and 0059.

Captures the exact state the DOCS -> RECORDS conversion depends on, so the
post-migration verifier can prove nothing was lost or double-counted. Writes a
JSON snapshot plus a readable summary.

This script NEVER writes: it opens the connection read-only, runs SELECTs only,
and rolls back. It is safe to run against live production.

SCHEMA AWARENESS
    The whole point of running this BEFORE the batch is that the new columns do
    not exist yet. At 0056/0057 `work_report_tasks.records_count` is absent, so
    the script inspects information_schema first and builds different SQL
    accordingly. A CASE expression would not help: PostgreSQL parses every
    column reference in a statement even on branches that never execute, so a
    missing column raises UndefinedColumn regardless.

    python scripts/migration_preflight_0057_0059.py --out preflight.json
    python scripts/migration_preflight_0057_0059.py --database-url postgresql+psycopg://...

Exit codes
    0  safe to proceed (JSON written, path printed)
    1  a gate failed - DO NOT MIGRATE (no snapshot written)
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

# Revisions this batch can legitimately start from, and what each implies.
#   0056/0057 -> the PAGES/RECORDS columns do not exist yet (the normal case)
#   0058/0059 -> partially/fully applied; columns exist and are read for real
REV_0056 = "0056_work_items"
REV_0057 = "0057_reconcile_activity_requests"
REV_0058 = "0058_pages_records_units"
REV_0059 = "0059_activity_req_pages_records"
PRE_0058_REVISIONS = {REV_0056, REV_0057}
ACCEPTED_REVISIONS = {REV_0056, REV_0057, REV_0058, REV_0059}
EXPECTED_HEAD = REV_0059

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

# Columns whose presence changes the SQL this script may emit.
CAPABILITY_COLUMNS = [
    ("work_report_tasks", "pages_count"),
    ("work_report_tasks", "records_count"),
    ("activity_requests", "pages_count"),
    ("activity_requests", "records_count"),
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


def detect_schema(conn) -> dict[str, bool]:
    """Which of the new columns physically exist right now.

    Resolved against the connection's own search_path so the answer matches the
    tables the later queries will actually hit."""
    caps: dict[str, bool] = {}
    for table, column in CAPABILITY_COLUMNS:
        exists = conn.execute(
            text(
                """
                SELECT count(*) > 0
                  FROM information_schema.columns
                 WHERE table_name = :t
                   AND column_name = :c
                   AND table_schema = ANY(current_schemas(false))
                """
            ),
            {"t": table, "c": column},
        ).scalar_one()
        caps[f"{table}_has_{column}"] = bool(exists)
    return caps


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

    caps = detect_schema(conn)
    out["schema"] = caps
    has_records = caps["work_report_tasks_has_records_count"]

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
    #
    # records_count is only mentioned in the SQL when it exists; before 0058 the
    # totals are zero by definition, not by coalesce.
    records_select = (
        "coalesce(sum(t.records_count), 0) AS records_total"
        if has_records
        else "0 AS records_total"
    )
    mixed_select = (
        "count(*) FILTER (WHERE t.docs_count > 0 AND t.records_count > 0) AS mixed_rows"
        if has_records
        else "0 AS mixed_rows"
    )

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
                    f"""
                    SELECT count(*)                       AS linked_task_count,
                           coalesce(sum(t.docs_count), 0) AS docs_total,
                           {records_select},
                           {mixed_select},
                           min(w.report_date)             AS min_report_date,
                           max(w.report_date)             AS max_report_date
                      FROM work_report_tasks t
                      JOIN daily_work_reports w ON w.id = t.report_id
                     WHERE t.sub_activity_id = CAST(:sid AS uuid)
                    """  # noqa: S608 - fragments are literals chosen above, never user input
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

    # A snapshot taken at/after 0058 is NOT a valid pre-migration baseline for
    # the postflight: its records totals already include the converted docs.
    out["is_pre_migration_baseline"] = out["alembic_current"] in PRE_0058_REVISIONS

    return out


def evaluate(snap: dict) -> list[tuple[bool, str]]:
    """Gates. Each is (ok, message); any False means DO NOT MIGRATE."""
    gates: list[tuple[bool, str]] = []

    cur = snap["alembic_current"]
    caps = snap["schema"]
    has_records = caps["work_report_tasks_has_records_count"]

    if cur == REV_0056:
        gates.append((True, f"alembic revision {cur} - full batch 0057/0058/0059 to apply"))
    elif cur == REV_0057:
        gates.append((True, f"alembic revision {cur} - 0058/0059 to apply"))
    elif cur == REV_0058:
        gates.append((True, f"alembic revision {cur} - partially applied, 0059 to apply"))
    elif cur == REV_0059:
        gates.append((True, f"alembic revision {cur} - already at head, nothing to apply"))
    else:
        gates.append((
            False,
            f"alembic revision {cur!r} is UNEXPECTED (want one of {sorted(ACCEPTED_REVISIONS)})",
        ))

    # --- schema drift -------------------------------------------------------
    # Before 0058 the new columns should not exist. If one does, someone changed
    # the schema outside Alembic. That is reportable drift, but harmless while
    # the column holds no data - so it only fails when data is actually present.
    if cur in PRE_0058_REVISIONS:
        drifted = [k for k, v in caps.items() if v]
        if not drifted:
            gates.append((True, "schema matches revision - new count columns absent as expected"))
        else:
            stray = sum(int(t.get("records_total") or 0) for t in snap["target_activities"])
            gates.append((
                stray == 0,
                f"SCHEMA DRIFT: {drifted} exist before 0058 "
                + (f"but hold no data (records_total={stray}) - reporting only"
                   if stray == 0 else
                   f"AND already hold data (records_total={stray}) - UNSAFE"),
            ))
    elif has_records:
        gates.append((True, "schema matches revision - new count columns present"))
    else:
        gates.append((
            False,
            f"revision {cur} implies the PAGES/RECORDS columns exist, but "
            "work_report_tasks.records_count is MISSING - schema/revision mismatch",
        ))

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

    # A row carrying BOTH docs and records on a to-be-converted activity cannot
    # be merged without ambiguity about which unit the historical value meant.
    mixed = sum(int(t.get("mixed_rows") or 0) for t in snap["target_activities"])
    gates.append((
        mixed == 0,
        f"{mixed} converted row(s) hold BOTH docs_count > 0 and records_count > 0"
        + ("" if mixed == 0 else " - UNSAFE to merge"),
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


def render(snap: dict, gates: list[tuple[bool, str]]) -> None:
    d = snap["database"]
    print("=" * 78)
    print("MIGRATION PREFLIGHT - 0057 / 0058 / 0059   (READ ONLY)")
    print("=" * 78)
    print(f"database        : {d['db']} @ {d['host']}:{d['port']} as {d['usr']}")
    print(f"captured        : {snap['captured_at']}")
    print(f"alembic current : {snap['alembic_current']}")
    print(f"alembic head    : {snap['alembic_expected_head']}")
    print()
    print("-- schema capabilities " + "-" * 55)
    for k, v in snap["schema"].items():
        print(f"  {k:<42} {str(v).lower()}")
    if not snap["is_pre_migration_baseline"]:
        print("  NOTE: taken at/after 0058 - NOT a valid pre-migration baseline")
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
        print(f"  mixed rows    : {t['mixed_rows']}")
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

    render(snap, gates)

    if failed:
        # No snapshot on failure: a half-trusted baseline is worse than none.
        print("Preflight FAILED")
        print("No snapshot written")
        print("Database unchanged")
        return 1

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2, default=_json_default)
    print(f"snapshot written: {os.path.abspath(args.out)}")
    print("RESULT: SAFE TO MIGRATE")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"PREFLIGHT ERROR: {exc}", file=sys.stderr)
        print("Preflight FAILED")
        print("No snapshot written")
        print("Database unchanged")
        raise SystemExit(2) from exc
