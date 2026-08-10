/**
 * Project Detail tab policy — visibility, fallback and direct-URL protection.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So these tests pin the pure policy the page renders from —
 * `buildProjectTabs` produces the exact tab list `<Tabs items=…>` receives, and
 * `resolveProjectTab` produces the exact value the page renders — rather than
 * mounting the component. Adding a component-test framework is out of scope for
 * this phase.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildProjectTabs,
  canSeeProjectTab,
  resolveProjectTab,
  PROJECT_DEFAULT_TAB,
  PROJECT_TAB_PARAM,
  type ProjectTabViewer,
} from "./tabs.ts";

// The three viewer kinds from the Phase 1 permission matrix.
const HEAD: ProjectTabViewer = { canManage: false, isHead: true };
const PM: ProjectTabViewer = { canManage: true, isHead: false };
const VIEWER: ProjectTabViewer = { canManage: false, isHead: false };

function labels(viewer: ProjectTabViewer): string[] {
  return buildProjectTabs(viewer).map((t) => t.label);
}

function values(viewer: ProjectTabViewer): string[] {
  return buildProjectTabs(viewer).map((t) => t.value);
}

// Test 1 — Head
test("Head sees Overview, Tag Scope and Summary", () => {
  assert.deepEqual(labels(HEAD), ["Overview", "Tag Scope", "Summary"]);
});

// Test 2 — Project Manager
test("Project Manager sees Overview, Tag Scope and Summary", () => {
  assert.deepEqual(labels(PM), ["Overview", "Tag Scope", "Summary"]);
});

test("a Project Manager who is also the Head still gets one of each tab", () => {
  assert.deepEqual(labels({ canManage: true, isHead: true }), [
    "Overview",
    "Tag Scope",
    "Summary",
  ]);
});

// Test 3 — Other authorized project viewer
test("other project viewers see all three tabs, Tag Scope included", () => {
  // The scope and the reasons it changed are context contributors need. What
  // they cannot do is CHANGE it — that is canManageTagScope, gated inside the
  // tab on the Revise button, and enforced by the API on the write endpoint.
  assert.deepEqual(labels(VIEWER), ["Overview", "Tag Scope", "Summary"]);
  assert.equal(canSeeProjectTab("tag-scope", VIEWER), true);
});

// Test 4 — Removed tabs
test("no viewer is offered the retired Activities or Submissions tabs", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    const shown = [...labels(viewer), ...values(viewer)];
    assert.equal(shown.includes("Activities"), false);
    assert.equal(shown.includes("Submissions"), false);
    assert.equal(shown.includes("activities"), false);
    assert.equal(shown.includes("submissions"), false);
  }
});

// Test 5 — Overview stays open to everyone permitted to view the project
test("Overview is visible to every viewer and is the default tab", () => {
  assert.equal(PROJECT_DEFAULT_TAB, "overview");
  assert.equal(PROJECT_TAB_PARAM, "tab");
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(values(viewer)[0], "overview");
    assert.equal(canSeeProjectTab("overview", viewer), true);
    assert.equal(resolveProjectTab(null, viewer), "overview");
    assert.equal(resolveProjectTab(undefined, viewer), "overview");
    assert.equal(resolveProjectTab("overview", viewer), "overview");
  }
});

// Test 6 — Tag Scope is reachable for every viewer
test("every authorized viewer can activate Tag Scope", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(resolveProjectTab("tag-scope", viewer), "tag-scope");
  }
});

// Test 7 — Summary placeholder is reachable for everyone
test("every authorized viewer can activate Summary", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(canSeeProjectTab("summary", viewer), true);
    assert.equal(resolveProjectTab("summary", viewer), "summary");
  }
});

// Test 8 — no tab is manager-only any more, but the mechanism still works
test("a hand-typed tab value is still normalised for every viewer", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(resolveProjectTab("nonsense", viewer), "overview");
    // The retired values from bookmarked links fall back rather than blanking.
    assert.equal(resolveProjectTab("activities", viewer), "overview");
    assert.equal(resolveProjectTab("submissions", viewer), "overview");
  }
});

test("Tag Scope is matched exactly, so near-miss values also fall back", () => {
  assert.equal(resolveProjectTab("Tag-Scope", PM), "overview");
  assert.equal(resolveProjectTab("tag_scope", PM), "overview");
  assert.equal(resolveProjectTab("tagscope", PM), "overview");
});

// Test 9 — Old tab URLs
test("bookmarked activities/submissions URLs fall back to Overview", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(resolveProjectTab("activities", viewer), "overview");
    assert.equal(resolveProjectTab("submissions", viewer), "overview");
  }
});

test("unknown or empty tab values fall back to Overview instead of a blank page", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    assert.equal(resolveProjectTab("", viewer), "overview");
    assert.equal(resolveProjectTab("nonsense", viewer), "overview");
  }
});
