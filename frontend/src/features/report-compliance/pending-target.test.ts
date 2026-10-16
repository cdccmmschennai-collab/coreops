import assert from "node:assert/strict";
import { test } from "node:test";

import {
  earliestPendingDate,
  parseReportDateParam,
  pendingReportOutcome,
  pendingReportPath,
} from "./pending-target.ts";

test("a due date opens the form even when today also looks incomplete", () => {
  assert.deepEqual(
    pendingReportOutcome({ pending_dates: ["2026-10-15"], fraction_mismatch_today: true }),
    { kind: "open", path: "/work-reports/new?date=2026-10-15" },
  );
});

test("an incomplete today alone is not overdue and not 'completed'", () => {
  assert.deepEqual(
    pendingReportOutcome({ pending_dates: [], fraction_mismatch_today: true }),
    { kind: "today_incomplete" },
  );
});

test("nothing due and no warning is all done", () => {
  assert.deepEqual(
    pendingReportOutcome({ pending_dates: [], fraction_mismatch_today: false }),
    { kind: "all_done" },
  );
  assert.deepEqual(pendingReportOutcome(undefined), { kind: "all_done" });
});

test("one pending date opens the New report form with that date", () => {
  assert.equal(pendingReportPath(["2026-10-12"]), "/work-reports/new?date=2026-10-12");
});

test("repeated clicks walk the remaining dates earliest-first", () => {
  // Each click re-reads the server list; a submitted date drops out of it.
  assert.equal(
    pendingReportPath(["2026-10-12", "2026-10-13", "2026-10-15"]),
    "/work-reports/new?date=2026-10-12",
  );
  assert.equal(
    pendingReportPath(["2026-10-13", "2026-10-15"]),
    "/work-reports/new?date=2026-10-13",
  );
  assert.equal(pendingReportPath(["2026-10-15"]), "/work-reports/new?date=2026-10-15");
});

test("the earliest is chosen even when the list is not sorted", () => {
  assert.equal(earliestPendingDate(["2026-10-15", "2026-09-30", "2026-10-12"]), "2026-09-30");
});

test("no pending dates resolves to nothing, never a blank form", () => {
  assert.equal(pendingReportPath([]), null);
  assert.equal(pendingReportPath(undefined), null);
  assert.equal(pendingReportPath(null), null);
});

test("malformed entries are skipped rather than used", () => {
  assert.equal(earliestPendingDate(["garbage", "2026-10-13"]), "2026-10-13");
  assert.equal(pendingReportPath(["not-a-date"]), null);
});

test("a valid ISO date passes through unchanged", () => {
  assert.equal(parseReportDateParam("2026-10-12"), "2026-10-12");
  assert.equal(parseReportDateParam("2028-02-29"), "2028-02-29");
});

test("invalid date params are rejected", () => {
  for (const raw of [
    null,
    undefined,
    "",
    "2026-13-01",
    "2026-00-10",
    "2026-02-30",
    "2027-02-29",
    "2026-10-32",
    "2026-10-00",
    "10/12/2026",
    "2026-10-12T00:00:00Z",
    "2026-10-12'; drop",
  ]) {
    assert.equal(parseReportDateParam(raw), null, String(raw));
  }
});
