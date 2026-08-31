/**
 * Pure-logic tests for the "AUTO" report badge rule (Phase 3G).
 *
 * The badge is informational: it says the 01:00 generator produced the row
 * rather than the employee. It must never imply anything about editability,
 * which the API alone decides, and it must never be shown on a report somebody
 * actually wrote.
 *
 * Harness: `node --test` over src/**â€‹/*.test.ts (see package.json test:unit) -
 * plain TypeScript, no jsdom / React Testing Library. Both the report list and
 * the report detail page delegate the whole decision to isAutoReport, so the
 * rule is fully pinned here.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { isAutoReport } from "./report-origin.ts";

// --------------------------------------------------------------------------
// employee-authored reports: never badged
// --------------------------------------------------------------------------
test("an employee-authored report is not automatic", () => {
  assert.equal(isAutoReport({ origin: "employee" }), false);
});

// --------------------------------------------------------------------------
// generated reports: badged, whatever kind of day they cover
// --------------------------------------------------------------------------
test("an AUTO week-off report is automatic", () => {
  // Phase 3C: origin auto, day_status week_off, submitted, zero minutes.
  assert.equal(isAutoReport({ origin: "auto" }), true);
});

test("an AUTO leave report is automatic", () => {
  // Phase 3E: origin auto, day_status leave, submitted. Locked while the
  // leave is active - locking is the API's business, the badge shows either way.
  assert.equal(isAutoReport({ origin: "auto" }), true);
});

test("an edited AUTO report reopened as a draft is still automatic", () => {
  // The critical one. Editing a generated report reopens it to draft but does
  // NOT restamp origin, because reconciliation matches on origin = auto. If
  // the badge disappeared here, the row would look employee-authored while the
  // scheduler still treated it as its own.
  const reopened = { origin: "auto", status: "draft" };
  assert.equal(isAutoReport(reopened), true);
});

// --------------------------------------------------------------------------
// unknown / absent origin: no badge, no crash
// --------------------------------------------------------------------------
test("a report with no origin field is not automatic", () => {
  // A build served by an older backend, before origin was exposed.
  assert.equal(isAutoReport({}), false);
});

test("a null origin is not automatic", () => {
  assert.equal(isAutoReport({ origin: null }), false);
});

test("an unrecognised origin value is not automatic", () => {
  // A future origin this build does not know must not be guessed into AUTO.
  assert.equal(isAutoReport({ origin: "imported" }), false);
  assert.equal(isAutoReport({ origin: "" }), false);
});

test("origin matching is exact, not case- or whitespace-insensitive", () => {
  assert.equal(isAutoReport({ origin: "AUTO" }), false);
  assert.equal(isAutoReport({ origin: " auto" }), false);
});

test("a missing report does not crash the badge", () => {
  // The list and detail page both render while the query is still loading.
  assert.equal(isAutoReport(undefined), false);
  assert.equal(isAutoReport(null), false);
});
