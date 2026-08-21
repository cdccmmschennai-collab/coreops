/**
 * Per-project authority — who may edit, archive and see Tag Scope.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. `useProjectAuthority` resolves {canManage, isHead} from the auth
 * context and the project row; everything downstream of that — the Edit button,
 * the /edit page guard, the Tag Scope tab — reads the predicates pinned here,
 * so these tests cover the rule every one of those surfaces applies.
 *
 * The API enforces the same rule independently (backend authz.can_edit_project,
 * covered in backend/tests/test_project_edit_authorization.py).
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canArchiveProject,
  canEditProject,
  canManageTagScope,
  canViewProductionStatus,
  canViewTagScope,
  canViewWeeklyReport,
  isProjectAdmin,
  type ProjectViewer,
} from "./permissions.ts";

// A PM is a PM on every project; Head-ness is resolved per project, so
// "head of THIS project" and "head of some other project" are simply
// isHead: true / isHead: false against the project on screen.
const PM: ProjectViewer = { canManage: true, isHead: false };
const ASSIGNED_HEAD: ProjectViewer = { canManage: false, isHead: true };
const UNASSIGNED_HEAD: ProjectViewer = { canManage: false, isHead: false };
const MEMBER: ProjectViewer = { canManage: false, isHead: false };

test("a PM may edit any project", () => {
  assert.equal(canEditProject(PM), true);
});

test("the assigned Head may edit the project they Head", () => {
  assert.equal(canEditProject(ASSIGNED_HEAD), true);
});

test("a Head of another project may not edit this one", () => {
  // Heading project A resolves to isHead:false against project B, so the same
  // predicate that grants edit on A denies it on B.
  assert.equal(canEditProject(UNASSIGNED_HEAD), false);
});

test("contributors, leads, QC and plain members may not edit", () => {
  // None of the activity staffing roles set canManage or isHead, so they all
  // reduce to this one viewer shape.
  assert.equal(canEditProject(MEMBER), false);
});

test("a PM who also Heads the project is still allowed exactly once", () => {
  assert.equal(canEditProject({ canManage: true, isHead: true }), true);
});

// --- archive / delete stays PM-only (must not widen with edit) -------------
test("archive remains PM-only and is not granted to the assigned Head", () => {
  assert.equal(canArchiveProject(PM), true);
  assert.equal(canArchiveProject(ASSIGNED_HEAD), false);
  assert.equal(canArchiveProject(UNASSIGNED_HEAD), false);
  assert.equal(canArchiveProject(MEMBER), false);
});

test("edit and archive are genuinely different predicates", () => {
  // Guards against a refactor that collapses them back into one flag.
  assert.notEqual(canEditProject(ASSIGNED_HEAD), canArchiveProject(ASSIGNED_HEAD));
});

// --- Tag Scope: open to read, restricted to change -------------------------
test("every project viewer may READ tag scope", () => {
  assert.equal(canViewTagScope(), true);
});

test("changing tag scope is the same set as edit: PM or this project's Head", () => {
  for (const viewer of [PM, ASSIGNED_HEAD, UNASSIGNED_HEAD, MEMBER]) {
    assert.equal(canManageTagScope(viewer), canEditProject(viewer));
    assert.equal(canManageTagScope(viewer), isProjectAdmin(viewer));
  }
});

test("reading and changing are genuinely different rights", () => {
  // A plain member sees the scope and its history, and can change neither.
  assert.equal(canViewTagScope(), true);
  assert.equal(canManageTagScope(MEMBER), false);
  assert.equal(canManageTagScope(UNASSIGNED_HEAD), false);
});

// --- Weekly Report: the assigned Head, and only them ------------------------
test("only this project's assigned Head may open the Weekly Report", () => {
  assert.equal(canViewWeeklyReport(ASSIGNED_HEAD), true);
  assert.equal(canViewWeeklyReport(UNASSIGNED_HEAD), false);
  assert.equal(canViewWeeklyReport(MEMBER), false);
});

test("a PM does NOT get the Weekly Report by virtue of being a PM", () => {
  // The narrowest rule on the page, and deliberately not the project-admin set:
  // this is a business decision, not an oversight.
  assert.equal(canViewWeeklyReport(PM), false);
  // A PM is a project ADMIN and still not a Weekly Report reader — the two sets
  // are deliberately different.
  assert.equal(isProjectAdmin(PM), true);
  // A PM who IS this project's Head qualifies — as its Head, not as a PM.
  assert.equal(canViewWeeklyReport({ canManage: true, isHead: true }), true);
});

// --- Production Status: PM / this project's Head / any of its activity Leads -
const ACTIVITY_LEAD: ProjectViewer = {
  canManage: false,
  isHead: false,
  leadsAnyActivity: true,
};

test("PM, the assigned Head and an activity Lead may open Production Status", () => {
  assert.equal(canViewProductionStatus(PM), true);
  assert.equal(canViewProductionStatus(ASSIGNED_HEAD), true);
  assert.equal(canViewProductionStatus(ACTIVITY_LEAD), true);
});

test("a plain member and a Head of another project may NOT open Production Status", () => {
  // Narrower than tag-scope READ, which every project viewer gets.
  assert.equal(canViewProductionStatus(MEMBER), false);
  assert.equal(canViewProductionStatus(UNASSIGNED_HEAD), false);
  assert.equal(canViewTagScope(), true);
});

test("leadsAnyActivity defaults to false when a caller omits it", () => {
  // The field is optional so existing callers keep meaning what they meant;
  // omitting it must never accidentally grant access.
  assert.equal(canViewProductionStatus({ canManage: false, isHead: false }), false);
  assert.equal(
    canViewProductionStatus({ canManage: false, isHead: false, leadsAnyActivity: false }),
    false,
  );
});

test("Production Status sits between Weekly Report and Tag Scope in breadth", () => {
  // Wider than Weekly Report (Head-only): a PM and a Lead get it too.
  assert.equal(canViewWeeklyReport(PM), false);
  assert.equal(canViewProductionStatus(PM), true);
  assert.equal(canViewWeeklyReport(ACTIVITY_LEAD), false);
  assert.equal(canViewProductionStatus(ACTIVITY_LEAD), true);
  // Narrower than Tag Scope (everyone): a plain member is excluded.
  assert.equal(canViewProductionStatus(MEMBER), false);
});

test("an activity Lead gains Production Status and nothing else", () => {
  // Leading an activity is not project authority: no edit, no archive, no
  // tag-scope management, no Weekly Report.
  assert.equal(canEditProject(ACTIVITY_LEAD), false);
  assert.equal(canArchiveProject(ACTIVITY_LEAD), false);
  assert.equal(canManageTagScope(ACTIVITY_LEAD), false);
  assert.equal(isProjectAdmin(ACTIVITY_LEAD), false);
  assert.equal(canViewWeeklyReport(ACTIVITY_LEAD), false);
});

test("Weekly Report access is strictly narrower than tag-scope management", () => {
  for (const viewer of [PM, ASSIGNED_HEAD, UNASSIGNED_HEAD, MEMBER]) {
    if (canViewWeeklyReport(viewer)) {
      assert.equal(canManageTagScope(viewer), true);
    }
  }
  // ...and genuinely narrower, not the same predicate renamed.
  assert.notEqual(canViewWeeklyReport(PM), canManageTagScope(PM));
});
