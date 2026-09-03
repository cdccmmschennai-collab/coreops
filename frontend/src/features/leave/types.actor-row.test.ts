/**
 * The actor/routing rows on the Leave Request card (see `leaveActorRows`).
 *
 * Directly under Status: "Routed to" says who the request went to, and
 * "Approved by" / "Rejected by" says who actually ruled on it. A settled request
 * shows BOTH, because those are different questions with frequently different
 * answers. These tests pin the labels as well as the names, because the label is
 * the part that carries the meaning.
 *
 * The rows are informational. Nothing here decides whether Approve/Reject renders
 * - that is `canReviewLeave`, tested in types.review.test.ts and untouched by
 * this phase. The two are asserted to be independent below.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { canReviewLeave, leaveActorRows } from "./types.ts";
import type { LeaveActorRow, LeaveStatus } from "./types.ts";

const APPROVER = "NAINAR B";
const ROUTED_TO = "Alex Manager";

const row = (
  status: LeaveStatus,
  {
    manager_name = APPROVER,
    routed_to_name = ROUTED_TO,
  }: { manager_name?: string | null; routed_to_name?: string | null } = {},
) => ({ status, manager_name, routed_to_name });

const ALL_STATUSES: LeaveStatus[] = [
  "pending",
  "approved",
  "rejected",
  "cancelled",
  "cancellation_requested",
];

const labelsOf = (rows: LeaveActorRow[]) => rows.map((r) => r.label);
const nameFor = (rows: LeaveActorRow[], label: string) =>
  rows.find((r) => r.label === label)?.name ?? null;

// ── 1. pending → Routed to ──────────────────────────────────────────────────

test("a pending request names who it is routed to", () => {
  assert.deepEqual(leaveActorRows(row("pending")), [
    { label: "Routed to", name: ROUTED_TO },
  ]);
});

test("a pending request shows no decision actor", () => {
  // Nobody has decided it yet; only the routing is meaningful.
  assert.deepEqual(labelsOf(leaveActorRows(row("pending"))), ["Routed to"]);
});

test("a pending request nobody could be routed to shows no row", () => {
  // Unrouted, requester has no reporting PM, or the only candidate has no login.
  assert.deepEqual(leaveActorRows(row("pending", { routed_to_name: null })), []);
  assert.deepEqual(leaveActorRows(row("pending", { routed_to_name: "  " })), []);
});

// ── 2./3. settled → Routed to AND Approved by / Rejected by ─────────────────

test("an approved request names its approver", () => {
  assert.deepEqual(leaveActorRows(row("approved")), [
    { label: "Routed to", name: ROUTED_TO },
    { label: "Approved by", name: APPROVER },
  ]);
});

test("a rejected request names its rejecter", () => {
  assert.deepEqual(leaveActorRows(row("rejected")), [
    { label: "Routed to", name: ROUTED_TO },
    { label: "Rejected by", name: APPROVER },
  ]);
});

test("a settled request keeps Routed to visible beside the decision", () => {
  for (const status of ["approved", "rejected"] as const) {
    assert.equal(nameFor(leaveActorRows(row(status)), "Routed to"), ROUTED_TO);
  }
});

test("the decision actor is never taken from the routing", () => {
  assert.equal(nameFor(leaveActorRows(row("approved")), "Approved by"), APPROVER);
  assert.equal(nameFor(leaveActorRows(row("rejected")), "Rejected by"), APPROVER);
});

test("a settled request whose actor has no name still names its routing", () => {
  // Historical rows decided before the reviewer was recorded. The missing half
  // is dropped, never guessed from the other.
  assert.deepEqual(leaveActorRows(row("approved", { manager_name: null })), [
    { label: "Routed to", name: ROUTED_TO },
  ]);
  assert.deepEqual(leaveActorRows(row("rejected", { manager_name: "" })), [
    { label: "Routed to", name: ROUTED_TO },
  ]);
});

test("a settled request with no recorded routing still names its actor", () => {
  assert.deepEqual(leaveActorRows(row("approved", { routed_to_name: null })), [
    { label: "Approved by", name: APPROVER },
  ]);
});

// ── 4. cancelled → no row ───────────────────────────────────────────────────

test("a cancelled request shows no actor row at all", () => {
  // `manager_name` on a cancelled row is its former APPROVER, and the person who
  // cancelled it is not recorded anywhere - so naming anybody here would name
  // the wrong one. Same rule the All-leave "By" column applies.
  assert.deepEqual(leaveActorRows(row("cancelled")), []);
});

test("a request awaiting a cancellation decision shows no actor row", () => {
  assert.deepEqual(leaveActorRows(row("cancellation_requested")), []);
});

// ── the whole rule ──────────────────────────────────────────────────────────

test("exactly three statuses produce rows, each with its own labels", () => {
  const labels: Record<string, string[]> = {};
  for (const status of ALL_STATUSES) {
    labels[status] = labelsOf(leaveActorRows(row(status)));
  }
  assert.deepEqual(labels, {
    pending: ["Routed to"],
    approved: ["Routed to", "Approved by"],
    rejected: ["Routed to", "Rejected by"],
    cancelled: [],
    cancellation_requested: [],
  });
});

test("no row is ever labelled the generic 'By' used by the All-leave table", () => {
  // The table needs one heading for mixed rows; the detail page has the status
  // in hand and says which decision it was.
  for (const status of ALL_STATUSES) {
    assert.equal(labelsOf(leaveActorRows(row(status))).includes("By"), false);
  }
});

// ── 6./7. seeing an actor is not being allowed to act ───────────────────────

test("the request owner sees the routing row but still gets no Review card", () => {
  const ME = "emp-1";
  const own = { ...row("pending"), employee_id: ME };
  // Told who has it...
  assert.deepEqual(labelsOf(leaveActorRows(own)), ["Routed to"]);
  // ...and still cannot act on it, even as an authorised reviewer.
  assert.equal(canReviewLeave(own, true, ME), false);
});

test("a reviewer looking at somebody else's pending request gets both", () => {
  const other = { ...row("pending"), employee_id: "emp-2" };
  assert.deepEqual(labelsOf(leaveActorRows(other)), ["Routed to"]);
  assert.equal(canReviewLeave(other, true, "emp-1"), true);
});

test("a plain employee viewing a settled request still sees the actor", () => {
  // Informational, not gated on review authority.
  const settled = { ...row("approved"), employee_id: "emp-1" };
  assert.equal(nameFor(leaveActorRows(settled), "Approved by"), APPROVER);
  assert.equal(canReviewLeave(settled, false, "emp-1"), false);
});
