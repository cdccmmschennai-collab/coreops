/**
 * Pure-logic tests for the LS (lumpsum) Count row: which unit owns the main
 * Count input, and which units are left to "Other counts".
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit) —
 * plain TypeScript, no jsdom / React Testing Library. The editor delegates both
 * decisions to primaryCountField / otherCountFields, so the rules are fully
 * pinned here even though the component itself cannot be mounted. The backend
 * enforces the same split independently (see backend
 * tests/test_lumpsum_count_field.py).
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { BenchmarkType } from "../activity-master/types.ts";
import {
  ALL_COUNT_FIELDS,
  COUNT_FIELD_OPTIONS,
  LUMPSUM_STAGED_COUNT,
  asCountField,
  countFieldName,
  countNeedsField,
  hasCountValue,
  isLumpsumUnitRow,
  lumpsumCountName,
  otherCountFields,
  primaryCountField,
} from "./ls-count.ts";

const LUMPSUM_MODES: BenchmarkType[] = ["TASK_STATUS_ONLY", "TASK_BASED"];

// ── the dropdown's own contents ──────────────────────────────────────────────

test("the Count dropdown offers exactly the six supported units", () => {
  assert.deepEqual(
    COUNT_FIELD_OPTIONS.map((o) => o.value),
    ["tags", "docs", "bom", "spares", "pages", "records"],
  );
  // Labels come from the shared map, not from a second list in the editor.
  assert.equal(COUNT_FIELD_OPTIONS[0].label, "Tags");
  assert.equal(COUNT_FIELD_OPTIONS[1].label, "Docs");
});

test("an unsupported field identifier is treated as nothing picked", () => {
  assert.equal(asCountField("tags"), "tags");
  assert.equal(asCountField(""), null);
  assert.equal(asCountField(null), null);
  assert.equal(asCountField("hours"), null);
  assert.equal(asCountField("tags_count"), null); // the column, not the unit
});

// ── which rows offer the Count + field dropdown ──────────────────────────────

for (const mode of LUMPSUM_MODES) {
  test(`${mode} with no configured unit is a lumpsum row`, () => {
    assert.equal(isLumpsumUnitRow(mode, null), true);
  });
}

test("a quantity mode is never a lumpsum row — its unit is the benchmark's", () => {
  assert.equal(isLumpsumUnitRow("NUMERIC_DAILY", "tags"), false);
  assert.equal(isLumpsumUnitRow("NUMERIC", "docs"), false);
  assert.equal(isLumpsumUnitRow("TASK_WITH_QUANTITY", "spares"), false);
  // No benchmark at all (LEAVE / TRAINING): no Count row either.
  assert.equal(isLumpsumUnitRow(null, null), false);
});

// ── the selected unit owns the Count input ───────────────────────────────────

test("an LS row with nothing picked yet has no main Count unit", () => {
  assert.equal(
    primaryCountField({
      benchmarkType: "TASK_STATUS_ONLY",
      relevantCountField: null,
      selectedCountField: "",
    }),
    null,
  );
});

test("picking Tags puts 25 under Tags; switching to Docs repoints the same row", () => {
  const row = (selectedCountField: string) =>
    primaryCountField({
      benchmarkType: "TASK_STATUS_ONLY",
      relevantCountField: null,
      selectedCountField,
    });
  assert.equal(row("tags"), "tags");
  assert.equal(countFieldName(row("tags")!), "tags_count");
  assert.equal(row("docs"), "docs");
  assert.equal(countFieldName(row("docs")!), "docs_count");
});

test("TASK_WITH_QUANTITY keeps the unit its benchmark configures", () => {
  // The configured unit wins even if a stale pick rides along on the row.
  assert.equal(
    primaryCountField({
      benchmarkType: "TASK_WITH_QUANTITY",
      relevantCountField: "spares",
      selectedCountField: "tags",
    }),
    "spares",
  );
  // And it is read from the master, so it is never one hardcoded field.
  for (const unit of ["tags", "docs", "bom", "spares", "pages", "records"] as const) {
    assert.equal(
      primaryCountField({
        benchmarkType: "TASK_WITH_QUANTITY",
        relevantCountField: unit,
        selectedCountField: null,
      }),
      unit,
    );
  }
});

test("a numeric daily row is unaffected by a count_field it never asked for", () => {
  assert.equal(
    primaryCountField({
      benchmarkType: "NUMERIC_DAILY",
      relevantCountField: "pages",
      selectedCountField: "records",
    }),
    "pages",
  );
});

// ── no duplicate input for the selected unit ─────────────────────────────────

test("the selected unit never appears again under Other counts", () => {
  assert.deepEqual(otherCountFields("tags"), [
    "docs_count", "bom_count", "spares_count", "pages_count", "records_count",
  ]);
  assert.deepEqual(otherCountFields("docs"), [
    "tags_count", "bom_count", "spares_count", "pages_count", "records_count",
  ]);
});

test("every unit behaves the same way, not just Tags and Docs", () => {
  for (const unit of ["tags", "docs", "bom", "spares", "pages", "records"] as const) {
    const others = otherCountFields(unit);
    assert.equal(others.length, ALL_COUNT_FIELDS.length - 1);
    assert.ok(!others.includes(countFieldName(unit)));
  }
});

test("Other counts still offers all six units while nothing is picked", () => {
  assert.deepEqual(otherCountFields(null), ALL_COUNT_FIELDS);
  assert.equal(otherCountFields(null).length, 6);
});

// ── where the Count input keeps its value ────────────────────────────────────

test("the Count input binds to the named unit, or to staging while unnamed", () => {
  assert.equal(lumpsumCountName("tags"), "tags_count");
  assert.equal(lumpsumCountName("records"), "records_count");
  // Nothing named yet: the employee can still type — the number waits here.
  assert.equal(lumpsumCountName(null), LUMPSUM_STAGED_COUNT);
});

// ── the conditional requirement ──────────────────────────────────────────────

test("a typed count is a value; empty and zero are not", () => {
  assert.equal(hasCountValue("25"), true);
  assert.equal(hasCountValue("1"), true);
  assert.equal(hasCountValue(""), false);
  assert.equal(hasCountValue("   "), false);
  // 0 is what an untouched unit already reads — not a count waiting for a field.
  assert.equal(hasCountValue("0"), false);
  assert.equal(hasCountValue(undefined), false);
  assert.equal(hasCountValue(null), false);
});

test("no count and no field is valid — the row saves", () => {
  assert.equal(countNeedsField("", ""), false);
});

test("a count with no field is not valid", () => {
  assert.equal(countNeedsField("25", ""), true);
  assert.equal(countNeedsField("25", null), true);
  // A field name the application does not support is no field at all.
  assert.equal(countNeedsField("25", "hours"), true);
});

test("a count that names its field is valid", () => {
  assert.equal(countNeedsField("25", "tags"), false);
  assert.equal(countNeedsField("50", "docs"), false);
});

test("a field with no count is valid — the count is never made mandatory", () => {
  assert.equal(countNeedsField("", "tags"), false);
  assert.equal(countNeedsField("0", "tags"), false);
});
