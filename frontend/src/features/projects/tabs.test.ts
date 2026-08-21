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

// The viewer kinds from the permission matrix.
const HEAD: ProjectTabViewer = { canManage: false, isHead: true };
const PM: ProjectTabViewer = { canManage: true, isHead: false };
const VIEWER: ProjectTabViewer = { canManage: false, isHead: false };
// Activity Lead: no project-level authority at all, but leads at least one
// activity on this project. Only Production Status consults this.
const LEAD: ProjectTabViewer = {
  canManage: false,
  isHead: false,
  leadsAnyActivity: true,
};

function labels(viewer: ProjectTabViewer): string[] {
  return buildProjectTabs(viewer).map((t) => t.label);
}

function values(viewer: ProjectTabViewer): string[] {
  return buildProjectTabs(viewer).map((t) => t.value);
}

// Test 1 — Head
test("Head sees Overview, Production Status, Tag Scope, Summary and Weekly Report", () => {
  assert.deepEqual(labels(HEAD), [
    "Overview",
    "Production Status",
    "Tag Scope",
    "Summary",
    "Weekly Report",
  ]);
});

// Test 2 — Project Manager
test("Project Manager sees everything except Weekly Report", () => {
  // Head-only by current requirement. A PM manages every project but does not
  // get this project's weekly operational report unless assigned as its Head.
  // Production Status IS included — the Phase 1 read rule gives a PM every
  // project's production status.
  assert.deepEqual(labels(PM), [
    "Overview",
    "Production Status",
    "Tag Scope",
    "Summary",
  ]);
});

test("a Project Manager who is also the Head still gets one of each tab", () => {
  assert.deepEqual(labels({ canManage: true, isHead: true }), [
    "Overview",
    "Production Status",
    "Tag Scope",
    "Summary",
    "Weekly Report",
  ]);
});

// Test 3 — Other authorized project viewer
test("other project viewers see the three open tabs, Tag Scope included", () => {
  // The scope and the reasons it changed are context contributors need. What
  // they cannot do is CHANGE it — that is canManageTagScope, gated inside the
  // tab on the Revise button, and enforced by the API on the write endpoint.
  assert.deepEqual(labels(VIEWER), ["Overview", "Tag Scope", "Summary"]);
  assert.equal(canSeeProjectTab("tag-scope", VIEWER), true);
});

// ---------- Weekly Report (Phase 7) ----------------------------------------
test("only this project's Head is offered Weekly Report", () => {
  assert.equal(canSeeProjectTab("weekly-report", HEAD), true);
  // A PM and an ordinary member are not — including a PM of every project and
  // someone who Heads a DIFFERENT project (isHead is resolved against the
  // project on screen, so heading another one reads as false here).
  assert.equal(canSeeProjectTab("weekly-report", PM), false);
  assert.equal(canSeeProjectTab("weekly-report", VIEWER), false);
  assert.equal(values(PM).includes("weekly-report"), false);
  assert.equal(values(VIEWER).includes("weekly-report"), false);
});

test("the tab order is Overview, Production Status, Tag Scope, Summary, Weekly Report", () => {
  // Phase 3 correction: Production Status moved up to sit directly after
  // Overview. Pinned here because order is what the page renders, and the only
  // place it is defined is tabs.ts's ALL_TABS.
  assert.deepEqual(values(HEAD), [
    "overview",
    "production-status",
    "tag-scope",
    "summary",
    "weekly-report",
  ]);
});

test("hiding a tab preserves the relative order of the rest", () => {
  // A viewer who loses Production Status and Weekly Report still sees the
  // remaining tabs in the same sequence - filtering never reshuffles.
  assert.deepEqual(values(VIEWER), ["overview", "tag-scope", "summary"]);
  assert.deepEqual(values(LEAD), [
    "overview",
    "production-status",
    "tag-scope",
    "summary",
  ]);
});

// ---------- Production Status (Phase 2) ------------------------------------
test("Production Status is offered to the PM, the Head and any activity Lead", () => {
  for (const viewer of [PM, HEAD, LEAD]) {
    assert.equal(canSeeProjectTab("production-status", viewer), true);
    assert.equal(values(viewer).includes("production-status"), true);
  }
});

test("a plain project member is NOT offered Production Status", () => {
  // Narrower than Tag Scope on purpose: a contributor or QC member can open the
  // project but not its production figures.
  assert.equal(canSeeProjectTab("production-status", VIEWER), false);
  assert.equal(values(VIEWER).includes("production-status"), false);
  assert.deepEqual(labels(VIEWER), ["Overview", "Tag Scope", "Summary"]);
});

test("an activity Lead gets Production Status but not Weekly Report", () => {
  assert.deepEqual(labels(LEAD), [
    "Overview",
    "Production Status",
    "Tag Scope",
    "Summary",
  ]);
  assert.equal(canSeeProjectTab("weekly-report", LEAD), false);
});

test("a hand-typed production-status URL falls back for an unauthorized viewer", () => {
  // Hiding the tab is not the protection: the value is normalised here, and all
  // three endpoints refuse the request regardless of what the client renders.
  assert.equal(resolveProjectTab("production-status", HEAD), "production-status");
  assert.equal(resolveProjectTab("production-status", PM), "production-status");
  assert.equal(resolveProjectTab("production-status", LEAD), "production-status");
  assert.equal(resolveProjectTab("production-status", VIEWER), "overview");
});

test("Production Status is matched exactly, so near-miss values fall back", () => {
  assert.equal(resolveProjectTab("Production-Status", HEAD), "overview");
  assert.equal(resolveProjectTab("production_status", HEAD), "overview");
  assert.equal(resolveProjectTab("productionstatus", HEAD), "overview");
});

test("adding Production Status left every other tab's visibility untouched", () => {
  for (const viewer of [HEAD, PM, VIEWER, LEAD]) {
    for (const tab of ["overview", "tag-scope", "summary"] as const) {
      assert.equal(canSeeProjectTab(tab, viewer), true, `${tab}`);
      assert.equal(resolveProjectTab(tab, viewer), tab);
    }
  }
  // Weekly Report is still Head-only, unchanged by the new tab.
  assert.equal(canSeeProjectTab("weekly-report", HEAD), true);
  assert.equal(canSeeProjectTab("weekly-report", PM), false);
  assert.equal(canSeeProjectTab("weekly-report", VIEWER), false);
});

test("a hand-typed weekly-report URL falls back for anyone but the Head", () => {
  // Hiding the tab is not the protection: the value is normalised here, and the
  // API refuses the request regardless of what the client renders.
  assert.equal(resolveProjectTab("weekly-report", HEAD), "weekly-report");
  assert.equal(resolveProjectTab("weekly-report", PM), "overview");
  assert.equal(resolveProjectTab("weekly-report", VIEWER), "overview");
});

test("adding Weekly Report left the other tabs' visibility untouched", () => {
  for (const viewer of [HEAD, PM, VIEWER]) {
    for (const tab of ["overview", "tag-scope", "summary"] as const) {
      assert.equal(canSeeProjectTab(tab, viewer), true, `${tab}`);
      assert.equal(resolveProjectTab(tab, viewer), tab);
    }
  }
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
