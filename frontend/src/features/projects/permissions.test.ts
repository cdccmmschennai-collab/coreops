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
  canViewTagScope,
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

// --- Tag Scope shares the edit predicate ----------------------------------
test("Tag Scope visibility is the same set as edit: PM or this project's Head", () => {
  for (const viewer of [PM, ASSIGNED_HEAD, UNASSIGNED_HEAD, MEMBER]) {
    assert.equal(canViewTagScope(viewer), canEditProject(viewer));
    assert.equal(canViewTagScope(viewer), isProjectAdmin(viewer));
  }
});
