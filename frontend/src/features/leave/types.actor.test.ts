/**
 * The "By" column of the All-leave table (see `leaveDecisionActor` in types.ts).
 *
 * The column is called "By" and not "Approved by" because the table holds
 * approved, rejected, cancelled and pending rows together. This helper decides
 * which of them actually name somebody, and it is the ONLY place that decision
 * is taken - the API always returns whatever actor the row genuinely records.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { leaveDecisionActor } from "./types.ts";
import type { LeaveStatus } from "./types.ts";

const ACTOR = "Priya Ramesh";

const row = (status: LeaveStatus, manager_name: string | null = ACTOR) => ({
  status,
  manager_name,
});

const ALL_STATUSES: LeaveStatus[] = [
  "pending",
  "approved",
  "rejected",
  "cancelled",
  "cancellation_requested",
];

// ── K/L. a settled decision names its reviewer ──────────────────────────────

test("an approved request shows the person who approved it", () => {
  assert.equal(leaveDecisionActor(row("approved")), ACTOR);
});

test("a rejected request shows the person who rejected it", () => {
  assert.equal(leaveDecisionActor(row("rejected")), ACTOR);
});

// ── M. cancelled is deliberately blank ──────────────────────────────────────

test("a cancelled request shows nothing, even though the row still has an actor", () => {
  // A leave approved and then withdrawn keeps its APPROVER in manager_name -
  // that is the honest record - but the cancellation was a different act by a
  // different person, which nothing records yet. Naming the approver here would
  // name the wrong one, so the table renders an em dash.
  assert.equal(leaveDecisionActor(row("cancelled")), null);
});

// ── N. nothing decided yet ──────────────────────────────────────────────────

test("a pending request shows nothing", () => {
  assert.equal(leaveDecisionActor(row("pending", null)), null);
});

test("a pending request shows nothing even if a name somehow came through", () => {
  assert.equal(leaveDecisionActor(row("pending")), null);
});

test("a request awaiting a cancellation decision shows nothing", () => {
  // The standing approval is under review again; there is no settled decision
  // to attribute.
  assert.equal(leaveDecisionActor(row("cancellation_requested")), null);
});

// ── the whole rule ──────────────────────────────────────────────────────────

test("approved and rejected are the ONLY statuses that name an actor", () => {
  for (const status of ALL_STATUSES) {
    const expected = status === "approved" || status === "rejected" ? ACTOR : null;
    assert.equal(leaveDecisionActor(row(status)), expected, status);
  }
});

// ── missing / unusable names fall back to blank ─────────────────────────────

test("a decision whose actor has no name resolves to nothing, not to 'null'", () => {
  // Historical rows decided before the reviewer was recorded, and rows whose
  // reviewer's employee record has since gone.
  assert.equal(leaveDecisionActor(row("approved", null)), null);
  assert.equal(leaveDecisionActor(row("rejected", null)), null);
});

test("a blank or whitespace name is treated as no name", () => {
  assert.equal(leaveDecisionActor(row("approved", "")), null);
  assert.equal(leaveDecisionActor(row("approved", "   ")), null);
});

test("a real name is returned untouched", () => {
  assert.equal(leaveDecisionActor(row("approved", "R. Sowrish Kumar")), "R. Sowrish Kumar");
});
