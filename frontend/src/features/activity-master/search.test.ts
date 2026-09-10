/**
 * Pure-logic tests for the Activity Master's unified hierarchical search.
 *
 * The component renders exactly what searchActivityMaster returns: the ranked
 * activity list, the parents to auto-expand, and the single row to scroll to
 * and flash. Pinning those three outputs pins the UI behaviour.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { normalizeSearchTerm, searchActivityMaster } from "./search.ts";
import type { ActivityMaster, SubActivityFlat } from "./types.ts";

function activity(id: string, name: string, code: string | null = null): ActivityMaster {
  return {
    id,
    parent_id: null,
    code,
    name,
    level: "activity",
    benchmark_type: null,
    benchmark_value: null,
    benchmark_period_days: null,
    benchmark_unit_note: null,
    benchmark_remarks: null,
    relevant_count_field: null,
    is_active: true,
    sort_order: 0,
    access_type: "COMMON",
    created_at: "2026-01-01T00:00:00Z",
  };
}

function sub(id: string, activityId: string, name: string): SubActivityFlat {
  return {
    id,
    activity_id: activityId,
    activity_name: "",
    name,
    benchmark_type: null,
    benchmark_value: null,
    benchmark_period_days: null,
    benchmark_unit_note: null,
    benchmark_remarks: null,
    relevant_count_field: null,
    is_active: true,
  };
}

// The user's own example hierarchy plus an MTL/FMTL pair for ranking.
const ARCH = activity("arch", "ARCHITECTURE & APPLICATION FOUNDATION");
const MTL = activity("mtl", "MTL - MATERIAL TESTING", "MTL");
const FMTL = activity("fmtl", "FMTL", "FMTL");
const TRAINING = activity("training", "TRAINING");
const ACTIVITIES = [ARCH, MTL, FMTL, TRAINING];

const SUBS = [
  sub("s1", "arch", "APPLICATION ARCHITECTURE"),
  sub("s2", "arch", "AUTHENTICATION & AUTHORIZATION FOUNDATION"),
  sub("s3", "arch", "BACKEND ARCHITECTURE"),
  sub("s4", "arch", "DATABASE ARCHITECTURE"),
  sub("s5", "arch", "FRONTEND ARCHITECTURE"),
  sub("s6", "arch", "REPORTING ARCHITECTURE"),
  sub("m1", "mtl", "MTL INSPECTION"),
  sub("m2", "mtl", "MTL PROCESS"),
  sub("f1", "fmtl", "FMTL INSPECTION"),
  sub("f2", "fmtl", "FMTL QC"),
  sub("t1", "training", "FMTL-FAMILIARIZATION"),
  sub("t2", "training", "DATABASE BASICS"),
];

const run = (term: string) => searchActivityMaster(ACTIVITIES, SUBS, term);
const ids = (r: ReturnType<typeof run>) => r.activities.map((x) => x.activity.id);

// ── normalization ─────────────────────────────────────────────────────────────

test("normalizeSearchTerm lower-cases, trims and collapses whitespace", () => {
  assert.equal(normalizeSearchTerm("  Database   ARCHITECTURE \t"), "database architecture");
  assert.equal(normalizeSearchTerm("   "), "");
});

test("an empty or whitespace-only term is not a search: full list, nothing expanded", () => {
  for (const term of ["", "   "]) {
    const r = run(term);
    assert.equal(r.active, false);
    assert.deepEqual(ids(r), ["arch", "mtl", "fmtl", "training"]);
    assert.deepEqual(r.expandActivityIds, []);
    assert.deepEqual(r.matchedSubActivityIds, []);
    assert.equal(r.primary, null);
  }
});

// ── activity search (existing behaviour preserved) ────────────────────────────

test("activity exact match", () => {
  const r = run("ARCHITECTURE & APPLICATION FOUNDATION");
  assert.equal(r.active, true);
  assert.equal(ids(r)[0], "arch");
  assert.equal(r.activities[0].activityTier, 0);
});

test("activity prefix match finds the activity, case-insensitively", () => {
  const r = run("architecture");
  assert.ok(ids(r).includes("arch"));
  assert.equal(r.activities.find((x) => x.activity.id === "arch")?.activityTier, 2);
});

test("activity partial (contains) match still finds the activity", () => {
  const r = run("APPLICATION FOUNDATION");
  assert.ok(ids(r).includes("arch"));
});

test("activity code is searchable", () => {
  const r = run("fmtl");
  assert.ok(ids(r).includes("fmtl"));
});

test("an activity that matched only by its own name is not auto-expanded", () => {
  const r = run("TRAINING");
  assert.deepEqual(ids(r), ["training"]);
  assert.deepEqual(r.expandActivityIds, []);
  assert.equal(r.primary, null);
});

// ── sub-activity search is hierarchical ───────────────────────────────────────

test("exact sub-activity match: parent is identified, auto-expanded, row is primary", () => {
  const r = run("DATABASE ARCHITECTURE");
  assert.deepEqual(ids(r), ["arch"]);
  assert.deepEqual(r.expandActivityIds, ["arch"]);
  assert.deepEqual(r.primary, { subActivityId: "s4", activityId: "arch" });
  // The matching row is present in the parent's hits (so it renders).
  const arch = r.activities[0];
  assert.deepEqual(arch.subHits.map((h) => h.sub.id), ["s4"]);
  assert.equal(arch.subHits[0].tier, 1);
});

test("partial sub-activity match reveals the parent and picks the row", () => {
  const r = run("database");
  // DATABASE ARCHITECTURE (arch) and DATABASE BASICS (training) both start
  // with the term; arch comes first in source order and holds the tie.
  assert.deepEqual(ids(r), ["arch", "training"]);
  assert.deepEqual(r.expandActivityIds, ["arch", "training"]);
  assert.deepEqual(r.primary, { subActivityId: "s4", activityId: "arch" });
});

test("a sub-activity never surfaces without its parent", () => {
  const orphan = sub("x", "missing-parent", "DATABASE ARCHITECTURE");
  const r = searchActivityMaster(ACTIVITIES, [...SUBS, orphan], "DATABASE ARCHITECTURE");
  assert.deepEqual(ids(r), ["arch"]);
  assert.ok(!r.matchedSubActivityIds.includes("x"));
});

// ── ranking ───────────────────────────────────────────────────────────────────

test("MTL ranks ahead of FMTL, deterministically", () => {
  const r = run("MTL");
  // MTL: exact code (tier 0). FMTL: contains only (tier 6), but its
  // sub "FMTL-FAMILIARIZATION" is a contains match too, and TRAINING only
  // matches through that sub - so it trails as well.
  assert.deepEqual(ids(r), ["mtl", "fmtl", "training"]);
  assert.equal(r.activities[0].bestTier, 0);
  assert.equal(r.activities[1].bestTier, 6);
  // Primary: the first MTL-prefixed sub-activity, never an FMTL one.
  assert.deepEqual(r.primary, { subActivityId: "m1", activityId: "mtl" });
});

test("a prefix hit ranks ahead of a mid-word contains hit even in source order", () => {
  const acts = [activity("a", "FMTL"), activity("b", "MTL PROCESS")];
  const r = searchActivityMaster(acts, [], "mtl");
  assert.deepEqual(ids(r), ["b", "a"]);
});

test("exact match beats prefix match", () => {
  const acts = [activity("a", "MTL INSPECTION"), activity("b", "MTL")];
  const r = searchActivityMaster(acts, [], "mtl");
  assert.deepEqual(ids(r), ["b", "a"]);
  assert.equal(r.activities[0].activityTier, 0);
  assert.equal(r.activities[1].activityTier, 2);
});

test("prefix match beats contains match", () => {
  const acts = [activity("a", "PROJECT MEETING-FMTL"), activity("b", "FMTL QC")];
  const r = searchActivityMaster(acts, [], "fmtl");
  assert.deepEqual(ids(r), ["b", "a"]);
});

test("exact sub-activity match beats an activity whose name merely starts with the phrase", () => {
  const acts = [activity("a", "DATABASE ARCHITECTURE FOUNDATION"), activity("b", "DATA")];
  const subs = [sub("s", "b", "DATABASE ARCHITECTURE")];
  const r = searchActivityMaster(acts, subs, "database architecture");
  assert.deepEqual(ids(r), ["b", "a"]);
  assert.deepEqual(r.primary, { subActivityId: "s", activityId: "b" });
});

test("word-start match ranks ahead of a mid-word contains match", () => {
  const subs = [sub("x", "arch", "XFMTL"), sub("y", "arch", "PROJECT MEETING-FMTL")];
  const r = searchActivityMaster([ARCH], subs, "fmtl");
  // Primary is the word-start hit (after the hyphen), not the mid-word one.
  assert.deepEqual(r.primary, { subActivityId: "y", activityId: "arch" });
});

test("ranking is by tier then source order - never alphabetical", () => {
  const acts = [activity("z", "MTL ZULU"), activity("a", "MTL ALPHA")];
  const r = searchActivityMaster(acts, [], "mtl");
  assert.deepEqual(ids(r), ["z", "a"]);
});

// ── multiple matches ──────────────────────────────────────────────────────────

test("multiple matching sub-activities under one activity all count, one primary", () => {
  const r = run("ARCHITECTURE");
  const arch = r.activities.find((x) => x.activity.id === "arch")!;
  assert.deepEqual(
    arch.subHits.map((h) => h.sub.id),
    ["s1", "s3", "s4", "s5", "s6"],
  );
  assert.ok(r.matchedSubActivityIds.includes("s1"));
  assert.ok(!r.matchedSubActivityIds.includes("s2"));
  assert.deepEqual(r.expandActivityIds, ["arch"]);
});

test("matching sub-activities under multiple activities expand only those parents", () => {
  const r = run("INSPECTION");
  assert.deepEqual(new Set(ids(r)), new Set(["mtl", "fmtl"]));
  assert.deepEqual(new Set(r.expandActivityIds), new Set(["mtl", "fmtl"]));
  assert.ok(!r.expandActivityIds.includes("arch"));
  assert.ok(!r.expandActivityIds.includes("training"));
});

test("an activity matched by name AND child is listed once and expanded", () => {
  const r = run("fmtl");
  const fmtl = r.activities.filter((x) => x.activity.id === "fmtl");
  assert.equal(fmtl.length, 1);
  assert.ok(r.expandActivityIds.includes("fmtl"));
  // TRAINING is only reached through FMTL-FAMILIARIZATION.
  assert.ok(r.expandActivityIds.includes("training"));
});

// ── clearing / no results ─────────────────────────────────────────────────────

test("clearing the term drops search expansion and the primary row", () => {
  const before = run("DATABASE ARCHITECTURE");
  assert.ok(before.expandActivityIds.length > 0 && before.primary !== null);
  const after = run("");
  assert.equal(after.active, false);
  assert.deepEqual(after.expandActivityIds, []);
  assert.equal(after.primary, null);
  assert.deepEqual(ids(after), ["arch", "mtl", "fmtl", "training"]);
});

test("no results yields an empty, still-active search (drives the empty state)", () => {
  const r = run("zzz-nothing");
  assert.equal(r.active, true);
  assert.deepEqual(r.activities, []);
  assert.deepEqual(r.expandActivityIds, []);
  assert.equal(r.primary, null);
});

test("search does not mutate its inputs", () => {
  const acts = [...ACTIVITIES];
  const subs = [...SUBS];
  run("ARCHITECTURE");
  assert.deepEqual(acts, ACTIVITIES);
  assert.deepEqual(subs, SUBS);
});
