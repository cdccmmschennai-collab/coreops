/**
 * Project Summary presentation (Phase 6) — search, cell formatting and the
 * three empty states.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So these tests pin the pure logic the tab renders from — the exact
 * strings `summary-tab.tsx` puts in each cell and the exact row list it maps
 * over — rather than mounting the component. Adding a component-test framework
 * is out of scope for this phase.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ACTIVITY_UNKNOWN,
  SUMMARY_NO_MATCH_TITLE,
  SUMMARY_SEARCH_PLACEHOLDER,
  VALUE_UNAVAILABLE,
  buildSummaryRows,
  filterSummaryRows,
  formatCount,
  formatReportedOfScope,
  matchesSummaryQuery,
  resolveSummaryState,
  type SummaryProgressRow,
} from "./summary.ts";

function row(
  activity: string | null,
  sub: string,
  reported: number,
  scope = 1200,
  id = sub,
): SummaryProgressRow {
  return {
    activity_id: activity ? `${activity}-id` : null,
    activity_name: activity,
    sub_activity_id: id,
    sub_activity_name: sub,
    reported_tags: reported,
    estimated_tag_count: scope,
    remaining_tags: Math.max(0, scope - reported),
  };
}

// The brief's project: scope 1,200, three independent progressions.
const API_ROWS: SummaryProgressRow[] = [
  row("DEMOLITION", "DEMOLITION-REWORK", 700),
  row("FMTL", "FMTL DATA POPULATION-SPIR DOC.NO/SPIR TAG NO", 400),
  row("MTL", "MTL-ASSET PHOTO DATA POPULATION", 40),
];
const ROWS = buildSummaryRows(API_ROWS);

// ---------- the four columns ----------
test("Activity and Sub-Activity are separate columns", () => {
  const r = ROWS[0];
  assert.equal(r.activityName, "DEMOLITION");
  assert.equal(r.subActivityName, "DEMOLITION-REWORK");
  // Never one merged label: the parent is its own cell, not a prefix parsed
  // back out of the sub-activity's name.
  assert.notEqual(r.activityName, r.subActivityName);
});

test("the parent Activity comes from the API, not from splitting the name", () => {
  // A sub-activity whose text shares nothing with its parent still shows it.
  const [only] = buildSummaryRows([row("FMTL", "TAG DESCRIPTION", 100)]);
  assert.equal(only.activityName, "FMTL");
  assert.equal(only.subActivityName, "TAG DESCRIPTION");
});

test("Reported / Scope renders both numbers with thousands separators", () => {
  assert.equal(ROWS[0].reportedOfScope, "700 / 1,200");
  assert.equal(ROWS[1].reportedOfScope, "400 / 1,200");
  assert.equal(ROWS[2].reportedOfScope, "40 / 1,200");
});

test("Remaining is the server's figure", () => {
  assert.equal(ROWS[0].remaining, "500");
  assert.equal(ROWS[1].remaining, "800");
  assert.equal(ROWS[2].remaining, "1,160");
});

test("rows are keyed by sub_activity_id, never by name", () => {
  const [a, b] = buildSummaryRows([
    row("MTL", "SAME NAME", 10, 1200, "id-1"),
    row("FMTL", "SAME NAME", 20, 1200, "id-2"),
  ]);
  assert.equal(a.key, "id-1");
  assert.equal(b.key, "id-2");
  assert.notEqual(a.key, b.key);
});

// ---------- the blank-Remaining regression ----------
test("40 of 1,200 remaining reads 1,160 and is never blank", () => {
  const r = ROWS[2];
  assert.equal(r.reportedOfScope, "40 / 1,200");
  assert.equal(r.remaining, "1,160");
  assert.notEqual(r.remaining, "");
});

test("no formatted cell is ever an empty string", () => {
  for (const r of ROWS) {
    for (const cell of [r.activityName, r.subActivityName, r.reportedOfScope, r.remaining]) {
      assert.equal(typeof cell, "string");
      assert.ok(cell.length > 0, `blank cell in ${r.key}`);
    }
  }
});

test("formatCount is total: nothing renders as blank, undefined or NaN", () => {
  // Every one of these is a value that used to be able to reach a cell.
  for (const bad of [null, undefined, NaN, Infinity, -Infinity, "", "12", {}, []]) {
    const out = formatCount(bad);
    assert.equal(out, VALUE_UNAVAILABLE, String(bad));
    assert.ok(out.length > 0);
    assert.ok(!out.includes("NaN") && !out.includes("undefined"));
  }
  assert.equal(formatCount(0), "0");
  assert.equal(formatCount(1160), "1,160");
});

test("a row with a missing remaining shows a placeholder, not an empty cell", () => {
  // A contract break (an older API, a bad deploy) must be visible, not silent.
  const broken = { ...row("MTL", "MTL-ASSET PHOTO DATA POPULATION", 40) };
  delete (broken as Partial<SummaryProgressRow>).remaining_tags;
  const [r] = buildSummaryRows([broken as SummaryProgressRow]);
  assert.equal(r.remaining, VALUE_UNAVAILABLE);
  assert.ok(r.remaining.length > 0);
});

test("a zero remaining renders as 0, not as an empty cell", () => {
  const [r] = buildSummaryRows([row("DEMOLITION", "DEMOLITION-REWORK", 1200)]);
  assert.equal(r.remaining, "0");
});

test("a sub-activity with no parent shows a placeholder Activity", () => {
  const [r] = buildSummaryRows([row(null, "ORPHANED SUB-ACTIVITY", 10)]);
  assert.equal(r.activityName, ACTIVITY_UNKNOWN);
  assert.ok(r.activityName.length > 0);
  // The progress itself is still shown rather than dropped.
  assert.equal(r.reportedOfScope, "10 / 1,200");
});

// ---------- independence ----------
test("each row measures against the whole scope independently", () => {
  // 700 + 400 + 40 is never presented as 1,140 / 1,200.
  assert.deepEqual(
    ROWS.map((r) => r.reportedOfScope),
    ["700 / 1,200", "400 / 1,200", "40 / 1,200"],
  );
  assert.deepEqual(ROWS.map((r) => r.remaining), ["500", "800", "1,160"]);
});

test("an over-reported row reads 0 remaining and is flagged, not hidden", () => {
  const [r] = buildSummaryRows([
    {
      ...row("DEMOLITION", "DEMOLITION-REWORK", 700, 500),
      remaining_tags: 0,
    },
  ]);
  assert.equal(r.reportedOfScope, "700 / 500");   // the real count, unchanged
  assert.equal(r.remaining, "0");                  // never negative
  assert.equal(r.overReported, true);
});

test("an ordinary row is not flagged", () => {
  assert.deepEqual(ROWS.map((r) => r.overReported), [false, false, false]);
});

// ---------- search ----------
test("search matches the Activity name", () => {
  const hits = filterSummaryRows(ROWS, "DEMOLITION");
  assert.deepEqual(hits.map((r) => r.subActivityName), ["DEMOLITION-REWORK"]);
});

test("search matches the Sub-Activity name", () => {
  const hits = filterSummaryRows(ROWS, "ASSET PHOTO");
  assert.deepEqual(hits.map((r) => r.activityName), ["MTL"]);
});

test("search is case-insensitive", () => {
  // Every casing of the same term returns the same rows.
  const expected = filterSummaryRows(ROWS, "MTL").map((r) => r.key);
  for (const q of ["mtl", "MTL", "MtL"]) {
    assert.deepEqual(filterSummaryRows(ROWS, q).map((r) => r.key), expected, q);
  }
  assert.deepEqual(
    filterSummaryRows(ROWS, "demolition-rework").map((r) => r.key),
    ["DEMOLITION-REWORK"],
  );
});

test("a substring match is honest about what contains it", () => {
  // "MTL" is literally inside "FMTL", so a partial-match search returns both
  // the MTL rows and the FMTL ones. That is the specified behaviour (partial,
  // not word-boundary): the user narrows further by typing more.
  const hits = filterSummaryRows(ROWS, "MTL").map((r) => r.activityName).sort();
  assert.deepEqual(hits, ["FMTL", "MTL"]);
  assert.deepEqual(filterSummaryRows(ROWS, "FMTL").map((r) => r.activityName), ["FMTL"]);
});

test("search matches partial words anywhere in the text", () => {
  assert.deepEqual(
    filterSummaryRows(ROWS, "REWORK").map((r) => r.subActivityName),
    ["DEMOLITION-REWORK"],
  );
  // Mid-string, not just a prefix.
  assert.equal(filterSummaryRows(ROWS, "SPIR DOC").length, 1);
  assert.equal(filterSummaryRows(ROWS, "PHOTO").length, 1);
});

test("FMTL matches through either column", () => {
  // Here the term is in both the Activity and the Sub-Activity; it must not
  // yield the row twice.
  const hits = filterSummaryRows(ROWS, "FMTL");
  assert.equal(hits.length, 1);
  assert.equal(hits[0].activityName, "FMTL");
});

test("a term found only in the Activity still returns the row", () => {
  const rows = buildSummaryRows([row("MTL", "ASSET PHOTO DATA POPULATION", 40)]);
  assert.equal(filterSummaryRows(rows, "MTL").length, 1);
});

test("no matches returns an empty list for the empty-state message", () => {
  assert.deepEqual(filterSummaryRows(ROWS, "XYZNOTFOUND"), []);
  assert.equal(
    SUMMARY_NO_MATCH_TITLE,
    "No matching activities or sub-activities found.",
  );
});

test("clearing the search restores every row", () => {
  assert.equal(filterSummaryRows(ROWS, "XYZNOTFOUND").length, 0);
  assert.equal(filterSummaryRows(ROWS, "").length, ROWS.length);
  // Whitespace is a cleared box too, not a search for a space.
  assert.equal(filterSummaryRows(ROWS, "   ").length, ROWS.length);
});

test("surrounding whitespace is trimmed before matching", () => {
  assert.equal(filterSummaryRows(ROWS, "  rework  ").length, 1);
});

test("the search box is labelled as covering both columns", () => {
  assert.equal(SUMMARY_SEARCH_PLACEHOLDER, "Search activity or sub-activity...");
});

test("matchesSummaryQuery agrees with the filter", () => {
  assert.equal(matchesSummaryQuery(ROWS[0], "demo"), true);
  assert.equal(matchesSummaryQuery(ROWS[0], "fmtl"), false);
  assert.equal(matchesSummaryQuery(ROWS[0], ""), true);
});

// ---------- empty states ----------
test("a normal project says tag scope does not apply", () => {
  const s = resolveSummaryState({ scope_type: "NONE", tag_progress: [] });
  assert.equal(s.kind, "not-tag-based");
  assert.equal(s.title, "This project does not use tag-based project scope.");
  // Never a fabricated 0 / 0.
  assert.ok(!s.title.includes("0"));
});

test("a tag project with no estimate says the scope is unconfigured", () => {
  const s = resolveSummaryState({
    scope_type: "TAG_BASED",
    estimated_tag_count: null,
    tag_progress: [],
  });
  assert.equal(s.kind, "unconfigured");
  assert.equal(s.title, "Tag scope has not been configured for this project yet.");
});

test("a scoped project with no reports says nothing has been reported", () => {
  const s = resolveSummaryState({
    scope_type: "TAG_BASED",
    estimated_tag_count: 1200,
    tag_progress: [],
  });
  assert.equal(s.kind, "nothing-reported");
  assert.equal(s.title, "No tag-based work has been reported for this project yet.");
});

test("the three empty states are worded differently from each other", () => {
  const titles = [
    resolveSummaryState({ scope_type: "NONE", tag_progress: [] }).title,
    resolveSummaryState({ scope_type: "TAG_BASED", tag_progress: [] }).title,
    resolveSummaryState({
      scope_type: "TAG_BASED",
      estimated_tag_count: 1200,
      tag_progress: [],
    }).title,
  ];
  assert.equal(new Set(titles).size, 3);
  for (const t of titles) assert.ok(t.length > 0);
});

test("rows present means the table state, whatever the scope fields say", () => {
  const s = resolveSummaryState({
    scope_type: "TAG_BASED",
    estimated_tag_count: 1200,
    tag_progress: API_ROWS,
  });
  assert.equal(s.kind, "table");
});

test("a reclassified project with a stale estimate still reads as not tag-based", () => {
  const s = resolveSummaryState({
    scope_type: "NONE",
    estimated_tag_count: 1200,
    tag_progress: [],
  });
  assert.equal(s.kind, "not-tag-based");
});

test("a missing or empty payload never crashes the tab", () => {
  assert.equal(resolveSummaryState(undefined).kind, "not-tag-based");
  assert.equal(resolveSummaryState(null).kind, "not-tag-based");
  assert.deepEqual(buildSummaryRows(undefined), []);
  assert.deepEqual(buildSummaryRows(null), []);
});

// ---------- scope guard: no drill-down in this phase ----------
test("a summary row carries exactly the four columns and nothing else", () => {
  // Pinned as an exact set: this is what stops employee-level or per-date
  // fields drifting into the Summary later. Those belong to a separate
  // surface, not to an expansion of this table.
  assert.deepEqual(Object.keys(ROWS[0]).sort(), [
    "activityId",
    "activityName",
    "key",
    "overReported",
    "remaining",
    "reportedOfScope",
    "subActivityId",
    "subActivityName",
  ]);
  const keys = Object.keys(ROWS[0]).join(" ").toLowerCase();
  for (const banned of ["employee", "contribution", "expand", "chevron"]) {
    assert.equal(keys.includes(banned), false, banned);
  }
});

test("formatReportedOfScope keeps both halves even when one is missing", () => {
  assert.equal(formatReportedOfScope(40, 1200), "40 / 1,200");
  assert.equal(formatReportedOfScope(null, 1200), "- / 1,200");
  assert.equal(formatReportedOfScope(40, null), "40 / -");
});
