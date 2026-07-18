"""Post-migration verifier for 0057 / 0058 / 0059.

Reads the JSON written by migration_preflight_0057_0059.py and proves the
DOCS -> RECORDS conversion moved every unit exactly once, lost no rows, and
left unrelated DOCS activities alone.

Read-only, like the preflight. Run it against the clone first, then against
production immediately after the real migration.

    python scripts/migration_postflight_0057_0059.py --preflight preflight.json

Exit codes
    0  every invariant PASSED
    1  one or more invariants FAILED
    2  could not connect / unexpected error
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from sqlalchemy import create_engine, text

EXPECTED_HEAD = "0059_activity_req_pages_records"


def _url(cli_url: str | None) -> str:
    url = cli_url or os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: pass --database-url or set DATABASE_URL", file=sys.stderr)
        raise SystemExit(2)
    return url


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--database-url", default=None)
    ap.add_argument("--preflight", required=True, help="JSON from the preflight run")
    args = ap.parse_args()

    with open(args.preflight, encoding="utf-8") as fh:
        pre = json.load(fh)

    engine = create_engine(_url(args.database_url))
    results: list[tuple[bool, str, str]] = []   # (ok, name, detail)

    def check(ok: bool, name: str, detail: str) -> None:
        results.append((bool(ok), name, detail))

    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))

        # 1 - revision reached the head
        cur = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one_or_none()
        check(cur == EXPECTED_HEAD, "alembic revision", f"{cur} (want {EXPECTED_HEAD})")

        # 2 - total task rows unchanged
        now_tasks = conn.execute(text("SELECT count(*) FROM work_report_tasks")).scalar_one()
        was_tasks = pre["totals"]["work_report_tasks"]
        check(now_tasks == was_tasks, "work_report_tasks row count unchanged",
              f"before={was_tasks} after={now_tasks}")

        # Per-target invariants, aggregated across the resolved rows.
        targets = pre["target_activities"]
        pre_docs = sum(int(t["docs_total"]) for t in targets)
        pre_records = sum(int(t["records_total"]) for t in targets)
        pre_ids: set[str] = {i for t in targets for i in t["task_ids"]}

        if not targets:
            check(False, "preflight had target activities", "none recorded - cannot verify")
        else:
            ids = [t["activity_master_id"] for t in targets]

            agg = conn.execute(
                text(
                    """
                    SELECT count(*)                          AS row_count,
                           coalesce(sum(t.docs_count), 0)    AS docs_total,
                           coalesce(sum(t.records_count), 0) AS records_total
                      FROM work_report_tasks t
                     WHERE t.sub_activity_id::text = ANY(:ids)
                    """
                ),
                {"ids": ids},
            ).mappings().one()

            # 3 - docs drained to zero on the converted activities
            check(int(agg["docs_total"]) == 0, "converted docs_count total is 0",
                  f"after={agg['docs_total']}")

            # 4 - records absorbed docs + any pre-existing records, exactly once
            expected_records = pre_docs + pre_records
            check(int(agg["records_total"]) == expected_records,
                  "converted records_count total == preflight docs + records",
                  f"expected={expected_records} after={agg['records_total']} "
                  f"(pre docs={pre_docs}, pre records={pre_records})")

            # 5 - snapshots relabelled to records
            snaps = conn.execute(
                text(
                    """
                    SELECT coalesce(t.relevant_count_field_snapshot, '(null)') AS snapshot,
                           count(*) AS n
                      FROM work_report_tasks t
                     WHERE t.sub_activity_id::text = ANY(:ids)
                     GROUP BY 1
                    """
                ),
                {"ids": ids},
            ).mappings().all()
            dist = {r["snapshot"]: r["n"] for r in snaps}
            non_records = {k: v for k, v in dist.items() if k != "records"}
            check(not non_records, "historical snapshots are 'records'",
                  f"distribution={dist}")

            # 6 - no task row disappeared
            now_ids = {
                str(x) for x in conn.execute(
                    text(
                        "SELECT id FROM work_report_tasks "
                        "WHERE sub_activity_id::text = ANY(:ids)"
                    ),
                    {"ids": ids},
                ).scalars().all()
            }
            missing = pre_ids - now_ids
            check(not missing, "no converted task ids disappeared",
                  f"before={len(pre_ids)} after={len(now_ids)} missing={len(missing)}"
                  + (f" e.g. {sorted(missing)[:3]}" if missing else ""))

            # 7 + 8 - unrelated DOCS untouched
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
                {"ids": ids},
            ).mappings().one()
            check(int(unrelated["row_count"]) == int(pre["unrelated_docs"]["row_count"]),
                  "unrelated DOCS row count unchanged",
                  f"before={pre['unrelated_docs']['row_count']} after={unrelated['row_count']}")
            check(int(unrelated["docs_total"]) == int(pre["unrelated_docs"]["docs_total"]),
                  "unrelated DOCS total unchanged",
                  f"before={pre['unrelated_docs']['docs_total']} after={unrelated['docs_total']}")

        conn.rollback()

    print("=" * 78)
    print("POST-MIGRATION VERIFIER - 0057 / 0058 / 0059")
    print("=" * 78)
    print(f"preflight snapshot: {args.preflight}")
    print(f"  captured        : {pre.get('captured_at')}")
    print(f"  source database : {pre.get('database', {}).get('db')}")
    print()
    width = max(len(n) for _, n, _ in results)
    for ok, name, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}  {detail}")
    failed = [n for ok, n, _ in results if not ok]
    print()
    print("RESULT:", "ALL INVARIANTS PASSED" if not failed else f"{len(failed)} FAILED: {failed}")
    return 0 if not failed else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"POSTFLIGHT ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
