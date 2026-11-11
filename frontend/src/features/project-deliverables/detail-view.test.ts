import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import {
  PROJECT_HEAD_TEXT,
  daysLeftLabel,
  projectHeadDisplay,
  projectHref,
  projectLabel,
} from "./detail-view.ts";

const ok = (data: { head_employee_id: string | null; head_employee_name: string | null }) => ({
  isLoading: false,
  isError: false,
  data,
});

test("Project Head shows the real assigned name from the project", () => {
  assert.deepEqual(
    projectHeadDisplay(ok({ head_employee_id: "e1", head_employee_name: "  Priya Raman " })),
    { kind: "assigned", name: "Priya Raman" },
  );
});

test("no Head assigned -> Not assigned", () => {
  const h = projectHeadDisplay(ok({ head_employee_id: null, head_employee_name: null }));
  assert.deepEqual(h, { kind: "not_assigned" });
  assert.equal(PROJECT_HEAD_TEXT.not_assigned, "Not assigned");
});

test("a failed or unresolved lookup is never reported as Not assigned", () => {
  assert.deepEqual(projectHeadDisplay({ isLoading: false, isError: true }), { kind: "unavailable" });
  assert.deepEqual(projectHeadDisplay({ isLoading: false, isError: false, data: null }), { kind: "unavailable" });
  // Head id present but no name resolved: we cannot name them, but one exists.
  assert.deepEqual(
    projectHeadDisplay(ok({ head_employee_id: "e1", head_employee_name: "" })),
    { kind: "unavailable" },
  );
  assert.deepEqual(projectHeadDisplay({ isLoading: true, isError: false }), { kind: "loading" });
});

test("project number is primary, description secondary, link is the project page", () => {
  const p = { project_id: "p-1", project_code: "4568-GC23109100", project_name: "Gas compression upgrade" };
  assert.deepEqual(projectLabel(p), { number: "4568-GC23109100", description: "Gas compression upgrade" });
  assert.equal(projectHref("p-1"), "/projects/p-1");
});

test("project label never renders an empty link", () => {
  assert.deepEqual(
    projectLabel({ project_id: "p-1", project_code: null, project_name: "Only a name" }),
    { number: "Only a name", description: null },
  );
  assert.deepEqual(
    projectLabel({ project_id: "p-1", project_code: null, project_name: null }),
    { number: "p-1", description: null },
  );
});

test("days-left corner label mirrors the backend's days_remaining", () => {
  const cases: [string, number | null, string | null][] = [
    ["on_track", 13, "13 days left"],
    ["due_soon", 2, "2 days left"],
    ["urgent", 1, "1 day left"],
    ["due_today", 0, "Due today"],
    ["overdue", -1, "1 day overdue"],
    ["overdue", -4, "4 days overdue"],
    ["no_deadline", null, null],
    ["completed", null, null],
  ];
  for (const [state, days, label] of cases) {
    assert.equal(daysLeftLabel({ deadline_state: state, days_remaining: days }), label);
  }
});

// No React render harness exists for `node --test`; guard layout + content at source level.
test("detail page source: two columns on desktop, details first, timeline preserved", () => {
  const src = readFileSync(
    fileURLToPath(new URL("./components/deliverable-detail.tsx", import.meta.url)),
    "utf8",
  );
  assert.match(src, /grid grid-cols-1 items-start gap-4 lg:grid-cols-2/);
  // DOM order = mobile stacking order: details card before the timeline.
  assert.ok(src.indexOf("<DetailsCard") < src.indexOf("<Timeline deliverableId"));
  for (const kept of [
    "Deliverable Details",
    "daysLeftLabel(deliverable)",
    'data-testid="deliverable-days-left"',
    'label="Project"',
    'label="Project Head"',
    'label="Activity"',
    'label="Planned Submission"',
    "projectHref(deliverable.project_id)",
    "useProject(deliverable.project_id)",
    "No changes recorded yet.",
    "Reason: {c.reason}",
    'c.changed_by_name || "System"',
    "has been delivered.",
    'href="/projects/deliverables"',
    "<DeliverableStatusBadge",
  ]) {
    assert.equal(src.includes(kept), true, `detail page must contain ${JSON.stringify(kept)}`);
  }
});
