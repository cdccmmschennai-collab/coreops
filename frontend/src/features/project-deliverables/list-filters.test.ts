import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  ALL,
  NO_FILTERS,
  PAGE_SIZE,
  UNASSIGNED,
  activityFilterOptions,
  assigneeFilterOptions,
  deliverableDetailHref,
  deliverableReturnHref,
  filterDeliverables,
  isFiltered,
  paginate,
  parseOffset,
  projectFilterOptions,
} from "./list-filters.ts";

type Role = "employee" | "project_head" | null;
const row = (
  id: string, project_id: string, project_code: string, project_name: string, name: string,
  status: "planned" | "completed", owner: [string, string, Role] | null = null,
) => ({
  id, project_id, project_code, project_name, name, status,
  owner_employee_id: owner?.[0] ?? null,
  owner_name: owner?.[1] ?? null,
  owner_role: owner?.[2] ?? null,
});

const rows = [
  row("1", "p1", "4568-GC23109100", "Gas Compression", "AD-NOC", "planned", ["e1", "Priya Raman", "employee"]),
  row("2", "p2", "P-412-LC24107700", "Liverpool Bay CCS", "EPIC FOR TRAFFIC SIGNAL", "planned", ["h2", "Arun Kumar", "project_head"]),
  row("3", "p2", "P-412-LC24107700", "Liverpool Bay CCS", "PROCESS FLOW AND QC WRITEUP", "completed"),
  row("4", "p1", "4568-GC23109100", "Gas Compression", "MDR VDR", "planned", ["e1", "Priya Raman", "employee"]),
];

const ids = (xs: { id: string }[]) => xs.map((x) => x.id);

// ── individual filters ─────────────────────────────────────────────────────

test("no filters returns everything, in order", () => {
  assert.deepEqual(ids(filterDeliverables(rows, NO_FILTERS)), ["1", "2", "3", "4"]);
  assert.equal(isFiltered(NO_FILTERS), false);
});

test("each filter narrows on its own", () => {
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, project: "p2" })), ["2", "3"]);
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, status: "planned" })), ["1", "2", "4"]);
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, activity: "MDR VDR" })), ["4"]);
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, assignee: "e1" })), ["1", "4"]);
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, assignee: "h2" })), ["2"]);
});

test("Unassigned matches rows with no Assignee only", () => {
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, assignee: UNASSIGNED })), ["3"]);
});

test("activity is an exact dropdown match; legacy empty value means all", () => {
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, activity: "MDR" })), []);
  assert.deepEqual(ids(filterDeliverables(rows, { ...NO_FILTERS, activity: "" })), ["1", "2", "3", "4"]);
  assert.equal(isFiltered({ ...NO_FILTERS, activity: "" }), false);
});

// ── combined filters + clear ───────────────────────────────────────────────

test("filters combine (AND) and each is preserved alongside the others", () => {
  assert.deepEqual(
    ids(filterDeliverables(rows, { ...NO_FILTERS, project: "p1", assignee: "e1", status: "planned" })),
    ["1", "4"],
  );
  assert.deepEqual(
    ids(filterDeliverables(rows, { project: "p1", activity: "AD-NOC", assignee: "e1", status: "planned" })),
    ["1"],
  );
  assert.deepEqual(
    ids(filterDeliverables(rows, { ...NO_FILTERS, project: "p2", assignee: "e1" })),
    [],
    "empty result when nothing matches all filters",
  );
});

test("isFiltered is true for any single active filter; clearing resets all", () => {
  for (const key of ["project", "activity", "assignee", "status"] as const) {
    assert.equal(isFiltered({ ...NO_FILTERS, [key]: "x" }), true, key);
  }
  assert.deepEqual(NO_FILTERS, { project: ALL, activity: ALL, assignee: ALL, status: ALL });
});

// ── dropdown options (searchable) ──────────────────────────────────────────

test("project options are distinct, sorted by code, searchable by name", () => {
  assert.deepEqual(projectFilterOptions(rows), [
    { value: "p1", label: "4568-GC23109100", keywords: ["Gas Compression"] },
    { value: "p2", label: "P-412-LC24107700", keywords: ["Liverpool Bay CCS"] },
  ]);
});

test("activity options are the distinct names, sorted", () => {
  assert.deepEqual(
    activityFilterOptions([...rows, { name: " MDR VDR " }]).map((o) => o.value),
    ["AD-NOC", "EPIC FOR TRAFFIC SIGNAL", "MDR VDR", "PROCESS FLOW AND QC WRITEUP"],
  );
});

test("assignee options: one per person, name only (no role), Unassigned last", () => {
  assert.deepEqual(assigneeFilterOptions(rows), [
    { value: "h2", label: "Arun Kumar" },
    { value: "e1", label: "Priya Raman" },
    { value: UNASSIGNED, label: "Unassigned" },
  ]);
});

test("the same person on two projects appears once", () => {
  const opts = assigneeFilterOptions([
    row("a", "p1", "C1", "N1", "X", "planned", ["e9", "Meena", "employee"]),
    row("b", "p2", "C2", "N2", "Y", "planned", ["e9", "Meena", "project_head"]),
  ]);
  assert.deepEqual(opts, [{ value: "e9", label: "Meena" }, { value: UNASSIGNED, label: "Unassigned" }]);
});

test("assignee options only list people present in the (already scoped) rows", () => {
  assert.deepEqual(assigneeFilterOptions([rows[2]]), [{ value: UNASSIGNED, label: "Unassigned" }]);
});


// ── pagination (offset/limit, same model as the shared <Pagination>) ──────

const many = Array.from({ length: 27 }, (_, i) => ({ id: String(i + 1) }));

test("10 per page, offsets 0 / 10 / 20", () => {
  assert.equal(PAGE_SIZE, 10);
  const p1 = paginate(many, 0);
  assert.deepEqual([p1.items.length, p1.offset, p1.limit, p1.total], [10, 0, 10, 27]);
  const p3 = paginate(many, 20);
  assert.deepEqual([p3.items.length, ids(p3.items)[0], p3.offset], [7, "21", 20]);
});

test("pages have no duplicates and no gaps", () => {
  const seen = [0, 10, 20].flatMap((o) => ids(paginate(many, o).items));
  assert.deepEqual(seen, ids(many));
});

test("fewer than 10 rows is one page; empty is safe", () => {
  const few = paginate(many.slice(0, 4), 0);
  assert.deepEqual([few.items.length, few.offset, few.total], [4, 0, 4]);
  const none = paginate([], 0);
  assert.deepEqual([none.items.length, none.offset, none.total], [0, 0, 0]);
});

test("out-of-range or invalid offsets snap to a real page", () => {
  assert.equal(paginate(many, 90).offset, 20);    // list shrank -> last page
  assert.equal(paginate(many, 13).offset, 10);    // mid-page -> page start
  assert.equal(paginate(many, -5).offset, 0);
  assert.equal(parseOffset("abc"), 0);
  assert.equal(parseOffset("-10"), 0);
  assert.equal(parseOffset(null), 0);
  assert.equal(parseOffset("20"), 20);
});

test("pagination applies after filtering", () => {
  const filtered = filterDeliverables(rows, { ...NO_FILTERS, assignee: "e1" });
  const p = paginate(filtered, 0);
  assert.deepEqual([p.total, ids(p.items)], [2, ["1", "4"]]);
});

// ── list -> detail -> back keeps filters + page ────────────────────────────

test("detail link carries the list URL and the back link restores it", () => {
  const from = "/projects/deliverables?project=p1&assignee=e1&offset=10";
  const href = deliverableDetailHref("d-1", from);
  assert.equal(href, `/projects/deliverables/d-1?from=${encodeURIComponent(from)}`);
  const raw = new URL(href, "http://x").searchParams.get("from");
  assert.equal(deliverableReturnHref(raw), from);
});

test("back link only ever returns to the Deliverables list", () => {
  assert.equal(deliverableDetailHref("d-1"), "/projects/deliverables/d-1");
  for (const bad of [null, "", "/attendance", "https://evil.example/projects/deliverables",
                     "//evil.example", "/projects/deliverables-x?a=1"]) {
    assert.equal(deliverableReturnHref(bad), "/projects/deliverables", String(bad));
  }
  assert.equal(deliverableReturnHref("/projects/deliverables"), "/projects/deliverables");
});

// ── view wiring (no React render harness under node --test) ────────────────

test("list view source: filter order, column order, page reset, shared pagination", () => {
  const src = readFileSync(
    fileURLToPath(new URL("./components/all-deliverables-view.tsx", import.meta.url)),
    "utf8",
  );
  const order = (labels: string[]) =>
    labels.map((l) => src.indexOf(l)).every((v, i, a) => v >= 0 && (i === 0 || v > a[i - 1]));
  assert.ok(
    order(['label="Project"', 'label="Activity"', 'label="Assignee"', 'label="Status"', "disabled={!filtered} onClick={clearFilters}"]),
    "filters must be Project | Activity | Assignee | Status | Clear",
  );
  assert.ok(
    order([
      "<TableHead>Project</TableHead>",
      "<TableHead>Activity</TableHead>",
      "<TableHead>Assignee</TableHead>",
      "<TableHead>Planned Submission</TableHead>",
      "<TableHead>Status</TableHead>",
      "Actions</TableHead>",
    ]),
    "columns must be Project | Activity | Assignee | Planned Submission | Status | Actions",
  );
  // Every filter change and Clear return to the first page.
  assert.match(src, /set\(v \|\| ALL\);\s*setOffsetParam\("0"\);/);
  assert.match(src, /setStatusFilter\(ALL\);\s*setOffsetParam\("0"\);/);
  assert.ok(src.includes("page.items.map((d)"));
  assert.ok(!src.includes("visible.map((d)"));
  // The SAME pagination control as every other table - not a new one.
  assert.ok(src.includes('import { Pagination } from "@/components/data/pagination"'));
  assert.ok(src.includes('useUrlState("offset", "0")'));
  assert.equal(src.includes("DeliverablesPagination"), false);
  // Rows open the detail WITH the return address.
  assert.ok(src.includes("deliverableDetailHref(id, here)"));
  // Responsive: stacked on mobile, 2-up on small, single row on large.
  assert.ok(src.includes("grid gap-3 sm:grid-cols-2 lg:grid-cols-[repeat(4,minmax(0,1fr))_auto]"));
  // Form: Activity Name and Assignee share one row (half width each), and
  // the Assignee is shown by name only - no role text anywhere.
  assert.match(src, /<FormItem>\s*<FormLabel>Activity Name \*<\/FormLabel>/);
  assert.match(src, /<FormItem>\s*<FormLabel>Assignee<\/FormLabel>/);
  assert.equal(src.includes("ASSIGNEE_ROLE_LABEL"), false);
  assert.equal(src.includes("a.role"), false);
  // Assignee terminology only.
  for (const banned of ["Associated Person", "Allocated Person", ">Owner<"]) {
    assert.equal(src.includes(banned), false, banned);
  }
});