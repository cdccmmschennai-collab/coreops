/**
 * Pure-logic tests for the Benchmark Guide search / sort / numbering pipeline.
 *
 * buildGuideRows is deliberately data-in / data-out (no hardcoded activities),
 * which is exactly what lets the guide reflect Activity Master changes with no
 * code edit. These tests pin that contract: a newly returned API row appears, a
 * changed benchmark value flows straight through, search matches the right
 * fields, and SL.No is assigned only after filtering + deterministic sorting.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { SubActivityFlat } from "../activity-master/types.ts";
import { buildGuideRows, resultCountLabel } from "./filter.ts";

let seq = 0;
function row(over: Partial<SubActivityFlat> = {}): SubActivityFlat {
  seq += 1;
  return {
    id: `s${seq}`,
    activity_id: `a${seq}`,
    activity_name: "ACT",
    name: "SUB",
    benchmark_type: null,
    benchmark_value: null,
    benchmark_period_days: null,
    benchmark_unit_note: null,
    benchmark_remarks: null,
    relevant_count_field: null,
    is_active: true,
    ...over,
  };
}

// ── data source: rows come from the input (the API), never a constant ─────────

test("output rows come only from the supplied API data", () => {
  assert.deepEqual(buildGuideRows([], {}), []);
  const rows = buildGuideRows([row({ id: "x", activity_name: "DOC IDB", name: "MDR" })], {});
  assert.equal(rows.length, 1);
  assert.equal(rows[0].id, "x");
});

test("a newly returned API activity appears with no code change", () => {
  const before = buildGuideRows([row({ activity_name: "A1", name: "S1" })], {});
  assert.equal(before.length, 1);
  // Simulate the next fetch returning an additional activity.
  const after = buildGuideRows(
    [row({ activity_name: "A1", name: "S1" }), row({ id: "new", activity_name: "ZZ New", name: "Fresh" })],
    {},
  );
  assert.equal(after.length, 2);
  assert.ok(after.some((r) => r.id === "new" && r.subActivityName === "Fresh"));
});

test("an updated benchmark value is reflected on the next build", () => {
  const base = { benchmark_type: "NUMERIC_DAILY" as const, relevant_count_field: "records" as const, benchmark_period_days: 1 };
  const first = buildGuideRows([row({ id: "b", benchmark_value: 250, ...base })], {});
  assert.equal(first[0].benchmark, "250");
  const second = buildGuideRows([row({ id: "b", benchmark_value: 300, ...base })], {});
  assert.equal(second[0].benchmark, "300");
});

// ── two independent searches: activity name vs sub-activity name ──────────────

// The parent-vs-child trap: "FMTL" appears as a PARENT activity, and also
// inside sub-activities under TRAINING / TRAINER / PROJECT MEETING.
const FMTL: SubActivityFlat[] = [
  row({ activity_name: "FMTL", name: "FMTL DATA POPULATION-FROM REFERENCE DOC", benchmark_type: "NUMERIC_DAILY", benchmark_value: 100, relevant_count_field: "tags", benchmark_period_days: 1 }),
  row({ activity_name: "FMTL", name: "FMTL QC", benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 1 }),
  row({ activity_name: "TRAINING", name: "FMTL-FAMILIARIZATION", benchmark_type: null }),
  row({ activity_name: "TRAINER", name: "FMTL-FAMILIARIZATION", benchmark_type: null }),
  row({ activity_name: "PROJECT MEETING", name: "PROJECT MEETING-FMTL", benchmark_type: null }),
];

test("Example A — Activity Search matches ONLY the parent activity name", () => {
  const r = buildGuideRows(FMTL, { activitySearch: "FMTL" });
  // Only the two rows whose PARENT activity is FMTL.
  assert.deepEqual(r.map((x) => x.subActivityName).sort(), ["FMTL DATA POPULATION-FROM REFERENCE DOC", "FMTL QC"]);
  // Must not surface sub-activities whose parent is TRAINING/TRAINER/PROJECT MEETING.
  assert.ok(r.every((x) => x.activityName === "FMTL"));
});

test("Activity Search does not match a token that only appears in sub names", () => {
  // "FAMILIARIZATION" lives only in sub-activity names, never a parent name.
  assert.deepEqual(buildGuideRows(FMTL, { activitySearch: "FAMILIARIZATION" }), []);
});

test("Example B — Sub-Activity Search matches ONLY the sub-activity name (any parent)", () => {
  const r = buildGuideRows(FMTL, { subActivitySearch: "FMTL" });
  // Every sub-activity name contains FMTL, so all five appear regardless of parent.
  assert.equal(r.length, 5);
  assert.ok(r.some((x) => x.activityName === "TRAINING"));
  assert.ok(r.some((x) => x.activityName === "TRAINER"));
  assert.ok(r.some((x) => x.activityName === "PROJECT MEETING"));
});

test("Sub-Activity Search does not match the parent activity name alone", () => {
  // "TRAINING" is a parent name but appears in no sub-activity name here.
  assert.deepEqual(buildGuideRows(FMTL, { subActivitySearch: "TRAINING" }), []);
});

test("Example C — both searches combine with AND", () => {
  const r = buildGuideRows(FMTL, { activitySearch: "TRAINING", subActivitySearch: "FMTL" });
  assert.equal(r.length, 1);
  assert.equal(r[0].activityName, "TRAINING");
  assert.equal(r[0].subActivityName, "FMTL-FAMILIARIZATION");
});

test("searches are case-insensitive and whitespace-trimmed", () => {
  const r = buildGuideRows(FMTL, { activitySearch: "  fmtl  " });
  assert.ok(r.length === 2 && r.every((x) => x.activityName === "FMTL"));
});

test("no results yields an empty list (drives the empty-results state)", () => {
  assert.deepEqual(buildGuideRows(FMTL, { subActivitySearch: "nonexistent-zzz" }), []);
});

// ── compact filters still work alongside the two searches ─────────────────────

const CORPUS: SubActivityFlat[] = [
  row({ activity_name: "DOC IDB", name: "MDR/VDR Consolidation", benchmark_type: "NUMERIC_DAILY", benchmark_value: 1000, relevant_count_field: "records", benchmark_period_days: 1 }),
  row({ activity_name: "MTL", name: "O&M Manuals Population", benchmark_type: "TASK_WITH_QUANTITY", benchmark_value: 500, relevant_count_field: "pages", benchmark_period_days: 1 }),
  row({ activity_name: "BOM IDB", name: "Audit Query with Report", benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 2 }),
];

test("unit filter keeps only rows on that unit", () => {
  const r = buildGuideRows(CORPUS, { unit: "records" });
  assert.equal(r.length, 1);
  assert.equal(r[0].unitField, "records");
});

test("mode filter keeps only rows in that mode (legacy folded in)", () => {
  const withLegacy = [...CORPUS, row({ activity_name: "LEG", name: "Legacy numeric", benchmark_type: "NUMERIC", benchmark_value: 10, relevant_count_field: "tags" })];
  const r = buildGuideRows(withLegacy, { mode: "numeric" });
  const names = r.map((x) => x.activityName).sort();
  assert.deepEqual(names, ["DOC IDB", "LEG"]);
});

test("unit and mode filters compose with the searches (AND)", () => {
  // Sub-Activity Search 'FMTL' across FMTL corpus, narrowed to numeric mode +
  // tags unit -> only the one NUMERIC_DAILY/tags row.
  const r = buildGuideRows(FMTL, { subActivitySearch: "FMTL", mode: "numeric", unit: "tags" });
  assert.equal(r.length, 1);
  assert.equal(r[0].subActivityName, "FMTL DATA POPULATION-FROM REFERENCE DOC");
});

// ── ordering + numbering ──────────────────────────────────────────────────────

test("rows sort by activity then sub-activity, independent of input order", () => {
  const shuffled = [
    row({ activity_name: "Beta", name: "z-last" }),
    row({ activity_name: "Alpha", name: "b" }),
    row({ activity_name: "Alpha", name: "a" }),
  ];
  const r = buildGuideRows(shuffled, {});
  assert.deepEqual(
    r.map((x) => `${x.activityName}/${x.subActivityName}`),
    ["Alpha/a", "Alpha/b", "Beta/z-last"],
  );
});

test("SL.No is regenerated after filtering + sorting (1..n, contiguous)", () => {
  const r = buildGuideRows(CORPUS, { activitySearch: "idb" }); // DOC IDB + BOM IDB
  assert.deepEqual(r.map((x) => x.no), [1, 2]);
  // BOM IDB sorts before DOC IDB, so numbering follows the sorted order.
  assert.equal(r[0].activityName, "BOM IDB");
  assert.equal(r[1].activityName, "DOC IDB");
});

// ── per-row display flags carried to the table ────────────────────────────────

test("rows carry the numeric-alignment flag and the full mode description", () => {
  const rows = buildGuideRows(CORPUS, {});
  const byActivity = (name: string) => rows.find((r) => r.activityName === name)!;

  // NUMERIC_DAILY / TASK_WITH_QUANTITY -> right-alignable number.
  assert.equal(byActivity("DOC IDB").isNumeric, true);
  assert.equal(byActivity("MTL").isNumeric, true);
  // TASK_STATUS_ONLY renders "Lump Sum" -> not numeric.
  assert.equal(byActivity("BOM IDB").isNumeric, false);
  assert.equal(byActivity("BOM IDB").benchmark, "Lump Sum");

  // Short label visible, full description available for tooltip / aria-label.
  assert.equal(byActivity("BOM IDB").mode, "Completion only");
  assert.equal(byActivity("BOM IDB").modeDescription, "Task - Completion Only");
});

// ── result count label ────────────────────────────────────────────────────────

test("result count reports visible-of-total with correct plural noun", () => {
  assert.equal(resultCountLabel(24, 146), "Showing 24 of 146 sub-activities");
  // Visible 1 keeps the plural noun because total (146) is plural.
  assert.equal(resultCountLabel(1, 146), "Showing 1 of 146 sub-activities");
});

test("result count uses the singular noun when the total is one", () => {
  assert.equal(resultCountLabel(1, 1), "Showing 1 of 1 sub-activity");
  assert.equal(resultCountLabel(0, 0), "Showing 0 of 0 sub-activities");
});

test("result count total is the API rows, visible updates as filters narrow", () => {
  // total = what the API returned (buildGuideRows input length), independent of
  // filtering; visible = the filtered row count. This mirrors how the dialog
  // computes `total` (query.data.length) vs `rows.length`.
  const total = FMTL.length; // 5 authorized/active rows from the API
  assert.equal(resultCountLabel(buildGuideRows(FMTL, {}).length, total), "Showing 5 of 5 sub-activities");
  assert.equal(
    resultCountLabel(buildGuideRows(FMTL, { activitySearch: "FMTL" }).length, total),
    "Showing 2 of 5 sub-activities",
  );
  assert.equal(
    resultCountLabel(buildGuideRows(FMTL, { activitySearch: "TRAINING", subActivitySearch: "FMTL" }).length, total),
    "Showing 1 of 5 sub-activities",
  );
});
