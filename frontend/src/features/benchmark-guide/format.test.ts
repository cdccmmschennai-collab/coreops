/**
 * Pure-logic tests for the Benchmark Guide human-readable formatting.
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit) —
 * plain TypeScript, no jsdom / React Testing Library. So this file pins the
 * formatting helper (formatBenchmark / benchmarkModeLabel / unitLabel /
 * formatBenchmarkNumber) that the guide table depends on. Component-interaction
 * behaviour (dialog open, window-focus refetch) needs a component-test
 * framework this project deliberately does not ship, and is asserted at the
 * backend/API and pure-pipeline layers instead.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { BenchmarkType, RelevantCountField, SubActivityFlat } from "../activity-master/types.ts";
import {
  benchmarkModeDescription,
  benchmarkModeLabel,
  benchmarkRemarks,
  formatBenchmark,
  formatBenchmarkNumber,
  isNumericBenchmark,
  resolveModeKey,
  unitLabel,
} from "./format.ts";

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

// ── mode labels, including the two legacy values ──────────────────────────────

test("short mode label maps every stored type (legacy values fold in)", () => {
  const cases: [BenchmarkType | null, string][] = [
    ["NUMERIC_DAILY", "Numeric daily"],
    ["NUMERIC", "Numeric daily"], // legacy -> same as NUMERIC_DAILY
    ["TASK_WITH_QUANTITY", "Quantity + completion"],
    ["TASK_STATUS_ONLY", "Completion only"],
    ["TASK_BASED", "Completion only"], // legacy -> same as TASK_STATUS_ONLY
    [null, "No benchmark"],
  ];
  for (const [type, label] of cases) {
    assert.equal(benchmarkModeLabel(type), label, `short mode for ${type}`);
  }
});

test("full mode description (tooltip / aria-label) keeps the technical wording", () => {
  const cases: [BenchmarkType | null, string][] = [
    ["NUMERIC_DAILY", "Numeric Daily"],
    ["NUMERIC", "Numeric Daily"],
    ["TASK_WITH_QUANTITY", "Task - Quantity + Completion"],
    ["TASK_STATUS_ONLY", "Task - Completion Only"],
    ["TASK_BASED", "Task - Completion Only"],
    [null, "No benchmark"],
  ];
  for (const [type, desc] of cases) {
    assert.equal(benchmarkModeDescription(type), desc, `description for ${type}`);
  }
});

test("resolveModeKey groups the five types into four modes", () => {
  assert.equal(resolveModeKey("NUMERIC"), "numeric");
  assert.equal(resolveModeKey("NUMERIC_DAILY"), "numeric");
  assert.equal(resolveModeKey("TASK_WITH_QUANTITY"), "task_quantity");
  assert.equal(resolveModeKey("TASK_BASED"), "task_completion");
  assert.equal(resolveModeKey("TASK_STATUS_ONLY"), "task_completion");
  assert.equal(resolveModeKey(null), "none");
});

// ── unit labels: all six supported units ──────────────────────────────────────

test("unit labels are title-case and human-readable for all six units", () => {
  const cases: [RelevantCountField, string][] = [
    ["tags", "Tags"],
    ["docs", "Docs"],
    ["bom", "BOM"],
    ["spares", "Spares"],
    ["pages", "Pages"],
    ["records", "Records"],
  ];
  for (const [field, label] of cases) assert.equal(unitLabel(field), label);
  assert.equal(unitLabel(null), null);
});

test("unit / period renders '<Unit> / Day' for every unit on a numeric daily", () => {
  const expected: [RelevantCountField, string][] = [
    ["tags", "Tags / Day"],
    ["docs", "Docs / Day"],
    ["bom", "BOM / Day"],
    ["spares", "Spares / Day"],
    ["pages", "Pages / Day"],
    ["records", "Records / Day"],
  ];
  for (const [field, up] of expected) {
    const f = formatBenchmark(
      row({ benchmark_type: "NUMERIC_DAILY", benchmark_value: 100, relevant_count_field: field, benchmark_period_days: 1 }),
    );
    assert.equal(f.unitPeriod, up);
  }
});

// ── number formatting ─────────────────────────────────────────────────────────

test("benchmark number strips trailing zeros", () => {
  assert.equal(formatBenchmarkNumber(250), "250");
  assert.equal(formatBenchmarkNumber("500.00"), "500");
  assert.equal(formatBenchmarkNumber(250.5), "250.5");
  assert.equal(formatBenchmarkNumber(null), "");
});

// ── the three worked examples from the spec ───────────────────────────────────

test("Numeric daily: 250 records/day", () => {
  const f = formatBenchmark(
    row({ benchmark_type: "NUMERIC_DAILY", benchmark_value: 250, relevant_count_field: "records", benchmark_period_days: 1 }),
  );
  assert.equal(f.benchmark, "250");
  assert.equal(f.unitPeriod, "Records / Day");
  assert.equal(f.mode, "Numeric daily");
  assert.equal(f.modeDescription, "Numeric Daily");
  assert.equal(f.isNumericBenchmark, true);
});

test("Task with quantity: 500 pages/day", () => {
  const f = formatBenchmark(
    row({ benchmark_type: "TASK_WITH_QUANTITY", benchmark_value: 500, relevant_count_field: "pages", benchmark_period_days: 1 }),
  );
  assert.equal(f.benchmark, "500");
  assert.equal(f.unitPeriod, "Pages / Day");
  assert.equal(f.mode, "Quantity + completion");
  assert.equal(f.modeDescription, "Task - Quantity + Completion");
  assert.equal(f.isNumericBenchmark, true);
  // No benchmark_remarks configured -> Remarks is empty, never a generated rule.
  assert.equal(f.remarks, "");
});

test("Status-only task: lump sum, complete within 2 days", () => {
  const f = formatBenchmark(row({ benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 2 }));
  assert.equal(f.benchmark, "Lump Sum");
  assert.equal(f.unitPeriod, "Complete within 2 days");
  assert.equal(f.mode, "Completion only");
  assert.equal(f.modeDescription, "Task - Completion Only");
  // "Lump Sum" is text, not a right-alignable number.
  assert.equal(f.isNumericBenchmark, false);
});

test("Status-only task singularizes a one-day period", () => {
  const f = formatBenchmark(row({ benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 1 }));
  assert.equal(f.unitPeriod, "Complete within 1 day");
});

test("no-benchmark row renders dashes, not raw fields", () => {
  const f = formatBenchmark(row({ benchmark_type: null }));
  assert.equal(f.benchmark, "-");
  assert.equal(f.unitPeriod, "-");
  assert.equal(f.mode, "No benchmark");
  assert.equal(f.isNumericBenchmark, false);
});

// ── numeric-benchmark alignment flag ──────────────────────────────────────────

test("isNumericBenchmark is true only for a numeric/quantity mode carrying a value", () => {
  // Numeric daily + quantity+completion with a value -> right-alignable number.
  assert.equal(
    isNumericBenchmark(row({ benchmark_type: "NUMERIC_DAILY", benchmark_value: 100, relevant_count_field: "tags" })),
    true,
  );
  assert.equal(
    isNumericBenchmark(row({ benchmark_type: "NUMERIC", benchmark_value: 10, relevant_count_field: "tags" })),
    true, // legacy numeric
  );
  assert.equal(
    isNumericBenchmark(row({ benchmark_type: "TASK_WITH_QUANTITY", benchmark_value: 500, relevant_count_field: "pages" })),
    true,
  );
  // Lump Sum (completion-only) and no-benchmark rows are NOT numeric.
  assert.equal(isNumericBenchmark(row({ benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 2 })), false);
  assert.equal(isNumericBenchmark(row({ benchmark_type: "TASK_BASED", benchmark_period_days: 2 })), false);
  assert.equal(isNumericBenchmark(row({ benchmark_type: null })), false);
});

// ── remarks: ONLY the Activity Master benchmark_remarks field ─────────────────

test("Remarks is exactly the trimmed benchmark_remarks value", () => {
  assert.equal(benchmarkRemarks(row({ benchmark_remarks: "  1DAY  " })), "1DAY");
  // The spec's worked example: configured "1DAY" is shown verbatim, never
  // auto-replaced with a generated sentence.
  const f = formatBenchmark(
    row({
      activity_name: "FMTL",
      name: "FMTL DATA POPULATION-FROM REFERENCE DOC...",
      benchmark_type: "NUMERIC_DAILY",
      benchmark_value: 100,
      relevant_count_field: "tags",
      benchmark_period_days: 1,
      benchmark_remarks: "1DAY",
    }),
  );
  assert.equal(f.benchmark, "100");
  assert.equal(f.unitPeriod, "Tags / Day");
  assert.equal(f.remarks, "1DAY");
});

test("blank or whitespace-only benchmark_remarks yields empty (table shows the placeholder)", () => {
  assert.equal(benchmarkRemarks(row({ benchmark_remarks: null })), "");
  assert.equal(benchmarkRemarks(row({ benchmark_remarks: "   " })), "");
});

test("benchmark_unit_note is NEVER used as the Remarks value", () => {
  const r = benchmarkRemarks(
    row({ benchmark_unit_note: "REQUIRED PAGES / DAY", benchmark_remarks: null }),
  );
  assert.equal(r, "");
});

test("no generated mode/completion sentence leaks into Remarks", () => {
  const r = benchmarkRemarks(
    row({
      benchmark_type: "TASK_WITH_QUANTITY",
      benchmark_value: 500,
      relevant_count_field: "pages",
      benchmark_period_days: 1,
      benchmark_remarks: null,
    }),
  );
  assert.equal(r, "");
});
