/**
 * Pins the PM Weekly Activity Report count-column contract shared by the
 * preview table and the Excel export (backend export.py _BLOCK):
 *
 *     Tags | Docs | BOM | Spares | Pages | Records
 *
 * Pages and Records must sit immediately after Spares (and, in the table, the
 * whole group sits before Remarks). sumCount must fall back to 0 for a legacy
 * activity that carries no pages/records value.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { COUNT_COLUMNS, sumCount } from "./columns.ts";
import type { ActivityCell } from "./types.ts";

test("count columns are in the exact contract order", () => {
  assert.deepEqual(
    COUNT_COLUMNS.map((c) => c.label),
    ["Tags", "Docs", "BOM", "Spares", "Pages", "Records"],
  );
  assert.deepEqual(
    COUNT_COLUMNS.map((c) => c.key),
    ["tags", "docs", "bom", "spares", "pages", "records"],
  );
});

test("Pages and Records sit immediately after Spares", () => {
  const labels = COUNT_COLUMNS.map((c) => c.label);
  assert.equal(labels[labels.indexOf("Spares") + 1], "Pages");
  assert.equal(labels[labels.indexOf("Pages") + 1], "Records");
});

test("sumCount adds a key across a day's activities", () => {
  const acts: ActivityCell[] = [
    { project_code: "P1", activity_type: "A", sub_activity_type: "S",
      tags: 1, docs: 2, bom: 3, spares: 4, pages: 10, records: 5 },
    { project_code: "P1", activity_type: "A", sub_activity_type: "S",
      tags: 1, docs: 2, bom: 3, spares: 4, pages: 15, records: 7 },
  ];
  assert.equal(sumCount(acts, "pages"), 25);
  assert.equal(sumCount(acts, "records"), 12);
});

test("sumCount treats a missing (legacy) pages/records value as 0", () => {
  // A row shaped like a legacy cell that predates the two columns.
  const legacy = {
    project_code: "P1", activity_type: "A", sub_activity_type: "S",
    tags: 1, docs: 2, bom: 3, spares: 4,
  } as unknown as ActivityCell;
  assert.equal(sumCount([legacy], "pages"), 0);
  assert.equal(sumCount([legacy], "records"), 0);
});
