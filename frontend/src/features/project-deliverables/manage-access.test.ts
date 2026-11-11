import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { canManageRow, creatableProjects } from "./manage-access.ts";

const PROJECTS = [
  { id: "p1", head_employee_id: "head-1" },
  { id: "p2", head_employee_id: "head-2" },
  { id: "p3", head_employee_id: null },
];

test("PM may add on every project", () => {
  assert.deepEqual(creatableProjects("project_manager", "pm-emp", PROJECTS).map((p) => p.id), ["p1", "p2", "p3"]);
});

test("a Project Head may add only on the projects they head", () => {
  assert.deepEqual(creatableProjects("employee", "head-1", PROJECTS).map((p) => p.id), ["p1"]);
  assert.deepEqual(creatableProjects("employee", "head-2", PROJECTS).map((p) => p.id), ["p2"]);
});

test("a plain member (heads nothing) gets no Add control", () => {
  assert.deepEqual(creatableProjects("employee", "someone-else", PROJECTS), []);
  assert.deepEqual(creatableProjects("employee", null, PROJECTS), []);
  assert.deepEqual(creatableProjects(undefined, "head-1", []), []);
});

test("Edit/Delete follow the backend's per-row can_manage", () => {
  assert.equal(canManageRow({ can_manage: true }), true);
  assert.equal(canManageRow({ can_manage: false }), false);
});

// No React render harness for `node --test`: guard the wiring at source level.
test("Deliverables page gates controls on can_manage, not the PM-only role check", () => {
  const src = readFileSync(
    fileURLToPath(new URL("./components/all-deliverables-view.tsx", import.meta.url)),
    "utf8",
  );
  assert.equal(src.includes('can(role, "project.manage")'), false);
  assert.ok(src.includes("creatableProjects("));
  assert.ok(src.includes("canManageRow(d)"));
  assert.ok(src.includes("deliverables.some(canManageRow)"));
});
