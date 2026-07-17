"""0058 PAGES/RECORDS units + benchmark mode split

Three separable changes, in one migration because the data step depends on both
schema steps:

1. SCHEMA — work_report_tasks gains ``pages_count`` / ``records_count``
   (INTEGER NOT NULL DEFAULT 0, matching tags/docs/bom/spares exactly).

2. SCHEMA — activity_master's CHECK constraints widen:
     * relevant_count_field: + 'pages', 'records'
     * benchmark_type:       + 'NUMERIC_DAILY', 'TASK_STATUS_ONLY',
                               'TASK_WITH_QUANTITY'
   The legacy 'NUMERIC' / 'TASK_BASED' values stay valid and are NOT rewritten
   in place — historical activity_master rows and the frozen
   work_report_tasks.benchmark_type_snapshot keep the value they were saved
   with. Both new constraint sets are strict supersets of the old ones, so no
   pre-existing row can be invalidated by adding them.

3. DATA — the six sub-activities listed by the business are reconfigured, and
   the three DOC IDB record-based ones have their historical DOCS counts moved
   to the new RECORDS column.

Why the DOCS -> RECORDS move is needed: a *document* and a *record* are
different measurable units. The three DOC IDB sub-activities below have always
counted records, but with no RECORDS unit available they were configured
against ``docs`` with the real unit stranded in the free-text
``benchmark_unit_note``. Their historical counts therefore sit in docs_count
and must move so that re-exported history reads under RECORDS and RECORDS never
offsets DOCS in a benchmark total.

SELECTION IS BY EXACT TRIMMED NAME, NOT BY HARDCODED UUID: the UUIDs differ
between the local database and production, so this migration resolves the rows
at runtime from (exact trimmed parent name, exact trimmed sub-activity name).
No ILIKE, no prefix matching, no "everything under DOC IDB" — sibling rows such
as DOC IDB-QC, DOC IDB-REWORK and DOC IDB-TYPE WISE... are genuinely
document-based and MUST remain under DOCS.

Inactive duplicates: a sub-activity that is inactive but carries the exact
approved parent+name is included ONLY when it has linked work_report_tasks
(i.e. it holds real history that must stay consistent). An unused inactive
duplicate is left alone.

Idempotent by construction. Per matching report row:
    docs > 0, records = 0  -> move docs into records, zero docs
    docs = 0, records > 0  -> already migrated; no-op
    docs = 0, records = 0  -> no quantity movement (snapshot still realigned)
    docs > 0, records > 0  -> ABORT (ambiguous; never merged or overwritten)
The move is an assignment (``records_count = docs_count``), never an
accumulation, so re-running can never double a count.

Revision ID: 0058_pages_records_units
Revises: 0057_reconcile_activity_requests
Create Date: 2026-07-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "0058_pages_records_units"
down_revision: Union[str, None] = "0057_reconcile_activity_requests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- the approved configuration (exact trimmed names) ----------------------
# parent activity name -> {sub-activity name: benchmark target}
_PAGES_PARENT = "MTL"
_PAGES_TARGETS = {
    "MTL-DOC.O&M MANNUALS DATA POPULATION": 500,
    "MTL-DOC.MATERIAL SUBMITTAL DATA POPULATION": 500,
    "MTL-DOC.MRIR/RFI/EPIC DATA POPULATION": 40,
}
_RECORDS_PARENT = "DOC IDB"
_RECORDS_TARGETS = {
    "DOC IDB-MDR/VDR CONSOLIDATION (DOC.TYPE/DOC.REQUIRED STATUS)": 1000,
    (
        "DOC IDB-DOC FILE PATH/POPULATION OF DOC.NO/DWG NO/TITLE/DOC.TYPE AND "
        "ORGANISING DOC.TYPE FOLDER IF MDR/VDR NOT AVAILABLE"
    ): 250,
    "DOC IDB-DOC FILE PATH MIGRATION WITH MDR/VDR AND MANUAL MATCHING": 400,
}

_BENCHMARK_TYPE_CK = "activity_master_benchmark_type_valid"
_COUNT_FIELD_CK = "activity_master_relevant_count_field_valid"
_REQUIRES_VALUE_CK = "activity_master_numeric_requires_value"
_REQUIRES_FIELD_CK = "activity_master_numeric_requires_count_field"


def _resolve_sub_activity_ids(bind, parent_name: str, sub_names) -> dict:
    """(exact trimmed parent name, exact trimmed sub-activity name) -> ids.

    Returns {sub_activity_name: [id, ...]} — a list per name because a name may
    legitimately resolve to several rows (an active row plus inactive historical
    duplicates that still carry report history; the DOC IDB-FAMILIARIZATION
    duplicate in the live database proves these exist).

    Inclusion rule, exactly as approved:
      * active row with the exact parent + exact name  -> always
      * INACTIVE row with the exact parent + exact name -> only when it has
        linked work_report_tasks (real history to keep consistent)
    btrim() on both sides tolerates stored whitespace without ever loosening the
    match to a partial one.
    """
    stmt = (
        text(
            """
            SELECT btrim(s.name) AS name, s.id AS id
            FROM activity_master s
            JOIN activity_master p ON p.id = s.parent_id
            WHERE s.level = 'sub_activity'
              AND btrim(p.name) = :parent_name
              AND btrim(s.name) IN :sub_names
              AND (
                    s.is_active = true
                    OR EXISTS (
                        SELECT 1 FROM work_report_tasks t
                        WHERE t.sub_activity_id = s.id
                    )
                  )
            """
        )
        .bindparams(sa.bindparam("sub_names", expanding=True))
    )
    rows = bind.execute(
        stmt, {"parent_name": parent_name, "sub_names": list(sub_names)}
    ).all()
    out: dict = {}
    for r in rows:
        out.setdefault(r.name, []).append(r.id)
    return out


def _flatten(resolved: dict) -> list:
    return [i for ids in resolved.values() for i in ids]


def _assert_no_docs_records_conflict(bind, ids: list) -> None:
    """Abort on any row carrying BOTH a meaningful docs_count and a meaningful
    records_count. Such a row cannot be resolved automatically: moving docs in
    would overwrite a real records value, and adding them together would invent
    a number nobody reported. Fail loudly with the exact task IDs instead."""
    if not ids:
        return
    stmt = (
        text(
            """
            SELECT id FROM work_report_tasks
            WHERE sub_activity_id IN :ids
              AND docs_count > 0
              AND records_count > 0
            ORDER BY id
            """
        )
        .bindparams(sa.bindparam("ids", expanding=True))
    )
    conflicts = [str(r.id) for r in bind.execute(stmt, {"ids": ids}).all()]
    if conflicts:
        raise RuntimeError(
            "0058 aborted: {n} work_report_tasks row(s) for the DOC IDB "
            "record-based sub-activities carry BOTH docs_count > 0 and "
            "records_count > 0. Migrating them would overwrite real data, and "
            "these values are never merged automatically. Resolve each row by "
            "hand, then re-run. Conflicting work_report_task ids: {ids}".format(
                n=len(conflicts), ids=", ".join(conflicts)
            )
        )


def _matching_totals(bind, ids: list) -> tuple:
    """(row_count, docs_sum, records_sum) over the matching report rows."""
    if not ids:
        return 0, 0, 0
    stmt = (
        text(
            """
            SELECT count(*) AS n,
                   coalesce(sum(docs_count), 0) AS docs,
                   coalesce(sum(records_count), 0) AS records
            FROM work_report_tasks
            WHERE sub_activity_id IN :ids
            """
        )
        .bindparams(sa.bindparam("ids", expanding=True))
    )
    r = bind.execute(stmt, {"ids": ids}).one()
    return int(r.n), int(r.docs), int(r.records)


def _unrelated_docs_sum(bind, ids: list) -> int:
    """docs_count sum over every row NOT being migrated — the invariant that
    proves no unrelated DOCS data was touched. The explicit IS NULL arm matters:
    `sub_activity_id NOT IN (...)` evaluates to NULL (not true) for a NULL
    sub_activity_id, which would silently drop those rows from the total."""
    if not ids:
        r = bind.execute(
            text("SELECT coalesce(sum(docs_count), 0) AS docs FROM work_report_tasks")
        ).one()
        return int(r.docs)
    stmt = (
        text(
            """
            SELECT coalesce(sum(docs_count), 0) AS docs
            FROM work_report_tasks
            WHERE sub_activity_id IS NULL OR sub_activity_id NOT IN :ids
            """
        )
        .bindparams(sa.bindparam("ids", expanding=True))
    )
    return int(bind.execute(stmt, {"ids": ids}).one().docs)


def migrate_docs_to_records(bind, ids: list) -> dict:
    """Move historical DOCS counts to RECORDS for exactly `ids`, with the
    conflict guard and the full invariant check. Extracted from upgrade() so the
    tests can drive it against synthetic rows on their own connection.

    Only the unit changes. employee, report, report date, project, task identity,
    completion state, benchmark_value_snapshot, benchmark_period_days_snapshot,
    deficit and productivity_pct are all untouched, so every historical
    achievement/pending figure stays numerically identical."""
    _assert_no_docs_records_conflict(bind, ids)

    before_rows, before_docs, before_records = _matching_totals(bind, ids)
    before_unrelated_docs = _unrelated_docs_sum(bind, ids)

    if ids:
        # Assignment, never accumulation: re-running can never double a count.
        # The records_count = 0 arm makes the already-migrated case a no-op.
        moved = bind.execute(
            text(
                """
                UPDATE work_report_tasks
                SET records_count = docs_count,
                    docs_count = 0
                WHERE sub_activity_id IN :ids
                  AND docs_count > 0
                  AND records_count = 0
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        ).rowcount
        # The frozen submit-time unit snapshot must follow the unit. Independent
        # of the counts: a zero-count row still reported against RECORDS.
        resnapped = bind.execute(
            text(
                """
                UPDATE work_report_tasks
                SET relevant_count_field_snapshot = 'records'
                WHERE sub_activity_id IN :ids
                  AND relevant_count_field_snapshot = 'docs'
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": ids},
        ).rowcount
    else:
        moved = resnapped = 0

    after_rows, after_docs, after_records = _matching_totals(bind, ids)
    after_unrelated_docs = _unrelated_docs_sum(bind, ids)

    # Invariants. Any failure raises and rolls the whole migration back (DDL is
    # transactional on Postgres), so a partial conversion can never be committed.
    if after_rows != before_rows:
        raise RuntimeError(
            f"0058 aborted: matching report row count changed "
            f"({before_rows} -> {after_rows}). No row may be created or deleted."
        )
    if after_docs != 0:
        raise RuntimeError(
            f"0058 aborted: matching DOCS sum is {after_docs}, expected 0 after "
            f"the move to RECORDS."
        )
    if after_records != before_docs + before_records:
        raise RuntimeError(
            f"0058 aborted: matching RECORDS sum is {after_records}, expected "
            f"{before_docs + before_records} (= DOCS {before_docs} + RECORDS "
            f"{before_records} before). Counts must be conserved exactly."
        )
    if after_unrelated_docs != before_unrelated_docs:
        raise RuntimeError(
            f"0058 aborted: DOCS sum for unrelated sub-activities changed "
            f"({before_unrelated_docs} -> {after_unrelated_docs}). Only the three "
            f"approved DOC IDB sub-activities may be converted."
        )

    return {
        "matching_rows": after_rows,
        "moved_rows": moved,
        "resnapshotted_rows": resnapped,
        "docs_before": before_docs,
        "records_before": before_records,
        "records_after": after_records,
        "unrelated_docs_sum": after_unrelated_docs,
    }


def _configure(bind, resolved: dict, targets: dict, *, benchmark_type: str, unit: str,
               set_period_days: int | None = None) -> int:
    """Point the resolved rows at the approved mode/unit/target. Remarks and
    benchmark_unit_note are deliberately preserved — they are supplementary
    display text the business wrote, not calculation inputs."""
    n = 0
    for name, ids in resolved.items():
        target = targets[name]
        params = {"ids": ids, "bt": benchmark_type, "unit": unit, "val": target}
        period_sql = ""
        if set_period_days is not None:
            period_sql = ", benchmark_period_days = :days"
            params["days"] = set_period_days
        n += bind.execute(
            text(
                f"""
                UPDATE activity_master
                SET benchmark_type = :bt,
                    relevant_count_field = :unit,
                    benchmark_value = :val
                    {period_sql}
                WHERE id IN :ids
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            params,
        ).rowcount
    return n


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. schema: the two new count columns ------------------------------
    # server_default="0" + nullable=False mirrors tags/docs/bom/spares exactly,
    # so existing rows backfill to 0 rather than NULL.
    op.add_column(
        "work_report_tasks",
        sa.Column("pages_count", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "work_report_tasks",
        sa.Column("records_count", sa.Integer(), server_default="0", nullable=False),
    )

    # --- 2. schema: widen the activity_master CHECK constraints ------------
    # Both replacements are supersets, so they can never reject an existing row.
    op.drop_constraint(_BENCHMARK_TYPE_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _BENCHMARK_TYPE_CK,
        "activity_master",
        "benchmark_type IS NULL OR benchmark_type IN "
        "('NUMERIC', 'TASK_BASED', 'NUMERIC_DAILY', 'TASK_STATUS_ONLY', "
        "'TASK_WITH_QUANTITY')",
    )
    op.drop_constraint(_COUNT_FIELD_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _COUNT_FIELD_CK,
        "activity_master",
        "relevant_count_field IS NULL OR relevant_count_field IN "
        "('tags', 'docs', 'bom', 'spares', 'pages', 'records')",
    )
    # The "needs a target"/"needs a unit" rules now cover every QUANTITY mode,
    # not just legacy NUMERIC. NOT IN yields NULL for a NULL benchmark_type, so
    # a no-benchmark row still passes — same semantics as the original form.
    op.drop_constraint(_REQUIRES_VALUE_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _REQUIRES_VALUE_CK,
        "activity_master",
        "benchmark_type NOT IN ('NUMERIC', 'NUMERIC_DAILY', 'TASK_WITH_QUANTITY') "
        "OR benchmark_value IS NOT NULL",
    )
    op.drop_constraint(_REQUIRES_FIELD_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _REQUIRES_FIELD_CK,
        "activity_master",
        "benchmark_type NOT IN ('NUMERIC', 'NUMERIC_DAILY', 'TASK_WITH_QUANTITY') "
        "OR relevant_count_field IS NOT NULL",
    )

    # --- 3. data: reconfigure the six approved sub-activities ---------------
    # A database without these rows (a fresh test DB, an office that never
    # loaded the master data) resolves to nothing and every step below no-ops.
    pages = _resolve_sub_activity_ids(bind, _PAGES_PARENT, _PAGES_TARGETS.keys())
    records = _resolve_sub_activity_ids(bind, _RECORDS_PARENT, _RECORDS_TARGETS.keys())

    # PAGES: a real deadline AND a real quantity -> TASK_WITH_QUANTITY. Their
    # 500/500/40 target previously existed only as free-text remarks, so
    # benchmark_value is being set for the first time here.
    _configure(
        bind, pages, _PAGES_TARGETS,
        benchmark_type="TASK_WITH_QUANTITY", unit="pages", set_period_days=1,
    )
    # RECORDS: daily production, not a carry-forward task -> NUMERIC_DAILY.
    # No completion checkbox, no due date, no work item. benchmark_period_days
    # is left as stored (already 1) — NUMERIC_DAILY is inherently per-day.
    _configure(
        bind, records, _RECORDS_TARGETS,
        benchmark_type="NUMERIC_DAILY", unit="records",
    )

    # --- 4. data: move historical DOCS counts to RECORDS -------------------
    migrate_docs_to_records(bind, _flatten(records))


def downgrade() -> None:
    """Reverts the schema and the six configurations, but REFUSES rather than
    destroy real data.

    There is no honest inverse for the DOCS -> RECORDS move once RECORDS is in
    use: a row's records_count may have been reported natively after this
    migration, so pushing RECORDS back into DOCS would fabricate document counts
    that were never reported, and would collide with any real docs_count. The
    same applies to PAGES. So the downgrade refuses whenever any PAGES/RECORDS
    quantity exists, or whenever a sub-activity outside the approved six has
    since been configured against those units (reverting it would require
    guessing which of the four legacy units it meant).

    When nothing uses the new units, the revert is exact and lossless: the six
    rows go back to their pre-0058 configuration, the snapshots realign, the
    constraints narrow and the two all-zero columns drop.

    A destructive downgrade is deliberately NOT provided for symmetry's sake.
    """
    bind = op.get_bind()

    in_use = bind.execute(
        text(
            "SELECT count(*) AS n FROM work_report_tasks "
            "WHERE pages_count <> 0 OR records_count <> 0"
        )
    ).one().n
    if in_use:
        raise RuntimeError(
            f"0058 downgrade refused: {in_use} work_report_tasks row(s) hold a "
            f"non-zero pages_count/records_count. Dropping those columns would "
            f"destroy reported production data, and moving the values back into "
            f"docs_count would fabricate document counts that were never "
            f"reported. Export or reconcile that data by hand first."
        )

    pages = _resolve_sub_activity_ids(bind, _PAGES_PARENT, _PAGES_TARGETS.keys())
    records = _resolve_sub_activity_ids(bind, _RECORDS_PARENT, _RECORDS_TARGETS.keys())
    known = _flatten(pages) + _flatten(records)

    stmt = "SELECT id, name FROM activity_master WHERE relevant_count_field IN ('pages', 'records')"
    params = {}
    if known:
        stmt += " AND id NOT IN :known"
        params["known"] = known
    q = text(stmt)
    if known:
        q = q.bindparams(sa.bindparam("known", expanding=True))
    strangers = bind.execute(q, params).all()
    if strangers:
        raise RuntimeError(
            "0058 downgrade refused: {n} sub-activit(y/ies) outside the six this "
            "migration configured now use the PAGES/RECORDS units, and there is "
            "no way to know which legacy unit they should revert to. Reconfigure "
            "them by hand first: {names}".format(
                n=len(strangers), names=", ".join(str(r.name) for r in strangers)
            )
        )

    # Realign the frozen unit snapshots before the units stop being valid. Safe:
    # every matching row is proven all-zero by the refusal check above, and all
    # six sub-activities were configured against 'docs' before 0058.
    if known:
        bind.execute(
            text(
                """
                UPDATE work_report_tasks
                SET relevant_count_field_snapshot = 'docs'
                WHERE sub_activity_id IN :ids
                  AND relevant_count_field_snapshot IN ('pages', 'records')
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": known},
        )

    # Restore the pre-0058 configuration exactly: the MTL trio were TASK_BASED
    # with NO benchmark_value (their 500/500/40 lived only in remarks); the DOC
    # IDB trio were NUMERIC against 'docs' keeping their 1000/250/400 target.
    if _flatten(pages):
        bind.execute(
            text(
                """
                UPDATE activity_master
                SET benchmark_type = 'TASK_BASED',
                    relevant_count_field = 'docs',
                    benchmark_value = NULL
                WHERE id IN :ids
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": _flatten(pages)},
        )
    if _flatten(records):
        bind.execute(
            text(
                """
                UPDATE activity_master
                SET benchmark_type = 'NUMERIC',
                    relevant_count_field = 'docs'
                WHERE id IN :ids
                """
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": _flatten(records)},
        )

    op.drop_constraint(_REQUIRES_FIELD_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _REQUIRES_FIELD_CK,
        "activity_master",
        "benchmark_type <> 'NUMERIC' OR relevant_count_field IS NOT NULL",
    )
    op.drop_constraint(_REQUIRES_VALUE_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _REQUIRES_VALUE_CK,
        "activity_master",
        "benchmark_type <> 'NUMERIC' OR benchmark_value IS NOT NULL",
    )
    op.drop_constraint(_COUNT_FIELD_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _COUNT_FIELD_CK,
        "activity_master",
        "relevant_count_field IS NULL OR relevant_count_field IN "
        "('tags', 'docs', 'bom', 'spares')",
    )
    op.drop_constraint(_BENCHMARK_TYPE_CK, "activity_master", type_="check")
    op.create_check_constraint(
        _BENCHMARK_TYPE_CK,
        "activity_master",
        "benchmark_type IS NULL OR benchmark_type IN ('NUMERIC', 'TASK_BASED')",
    )

    op.drop_column("work_report_tasks", "records_count")
    op.drop_column("work_report_tasks", "pages_count")
