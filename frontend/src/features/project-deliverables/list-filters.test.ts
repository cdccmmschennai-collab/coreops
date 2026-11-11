import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ALL,
  filterDeliverables,
  isFiltered,
  projectFilterOptions,
} from "./list-filters.ts";

const rows = [
  { id: "1", project_id: "p1", project_code: "4568-GC23109100", project_name: "A", name: "AD-NOC", status: "planned" as const },
  { id: "2", project_id: "p2", project_code: "P-412-LC24107700", project_name: "B", name: "EPIC FOR TRAFFIC SIGNAL", status: "planned" as const },
  { id: "3", project_id: "p2", project_code: "P-412-LC24107700", project_name: "B", name: "PROCESS FLOW AND QC WRITEUP", status: "completed" as const },
  { id: "4", project_id: "p1", project_code: "4568-GC23109100", project_name: "A", name: "MDR VDR", status: "planned" as const },
];

const none = { project: ALL, activity: "", status: ALL };
const ids = (xs: { id: string }[]) => xs.map((x) => x.id);

test("no filters returns everything, in order", () => {
  assert.deepEqual(ids(filterDeliverables(rows, none)), ["1", "2", "3", "4"]);
  assert.equal(isFiltered(none), false);
});

test("project, status and activity filters combine", () => {
  assert.deepEqual(ids(filterDeliverables(rows, { ...none, project: "p2" })), ["2", "3"]);
  assert.deepEqual(ids(filterDeliverables(rows, { ...none, status: "planned" })), ["1", "2", "4"]);
  assert.deepEqual(
    ids(filterDeliverables(rows, { project: "p2", activity: "", status: "planned" })),
    ["2"],
  );
});

test("activity search is case-insensitive and trims", () => {
  assert.deepEqual(ids(filterDeliverables(rows, { ...none, activity: "  qc " })), ["3"]);
  assert.equal(isFiltered({ ...none, activity: " " }), false);
  assert.equal(isFiltered({ ...none, activity: "mdr" }), true);
});

test("project options are distinct and sorted by code", () => {
  assert.deepEqual(projectFilterOptions(rows), [
    { id: "p1", label: "4568-GC23109100" },
    { id: "p2", label: "P-412-LC24107700" },
  ]);
});
