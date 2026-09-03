/**
 * The actor/routing row on the Leave Request card (see `leaveActorRow`).
 *
 * One row, directly under Status, whose LABEL depends on the status: "Routed to"
 * while the request is waiting, "Approved by" / "Rejected by" once it is
 * settled, and nothing at all otherwise. These tests pin the label as well as
 * the name, because the label is the part that carries the meaning.
 *
 * The row is informational. Nothing here decides whether Approve/Reject renders
 * - that is `canReviewLeave`, tested in types.review.test.ts and untouched by
 * this phase. The two are asserted to be independent below.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { canReviewLeave, leaveActorRow } from "./types.ts";
import type { LeaveStatus } from "./types.ts";

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

// ── 1. pending → Routed to ──────────────────────────────────────────────────

test("a pending request names who it is routed to", () => {
  assert.deepEqual(leaveActorRow(row("pending")), {
    label: "Routed to",
    name: ROUTED_TO,
  });
});

test("a pending request ignores any decision actor on the row", () => {
  // Nobody has decided it yet; only the routing is meaningful.
  assert.equal(leaveActorRow(row("pending"))?.name, ROUTED_TO);
});

test("a pending request nobody could be routed to shows no row", () => {
  // Unrouted, requester has no reporting PM, or the only candidate has no login.
  assert.equal(leaveActorRow(row("pending", { routed_to_name: null })), null);
  assert.equal(leaveActorRow(row("pending", { routed_to_name: "  " })), null);
});

// ── 2./3. settled → Approved by / Rejected by ───────────────────────────────

test("an approved request names its approver", () => {
  assert.deepEqual(leaveActorRow(row("approved")), {
    label: "Approved by",
    name: APPROVER,
  });
});

test("a rejected request names its rejecter", () => {
  assert.deepEqual(leaveActorRow(row("rejected")), {
    label: "Rejected by",
    name: APPROVER,
  });
});

test("a settled request ignores any stale routing name", () => {
  // The routing is spent once a decision exists - the question becomes who
  // decided, not who was holding it.
  assert.equal(leaveActorRow(row("approved"))?.name, APPROVER);
  assert.equal(leaveActorRow(row("rejected"))?.name, APPROVER);
});

test("a settled request whose actor has no name shows no row", () => {
  // Historical rows decided before the reviewer was recorded.
  assert.equal(leaveActorRow(row("approved", { manager_name: null })), null);
  assert.equal(leaveActorRow(row("rejected", { manager_name: "" })), null);
});

// ── 4. cancelled → no row ───────────────────────────────────────────────────

test("a cancelled request shows no actor row at all", () => {
  // `manager_name` on a cancelled row is its former APPROVER, and the person who
  // cancelled it is not recorded anywhere - so naming anybody here would name
  // the wrong one. Same rule the All-leave "By" column applies.
  assert.equal(leaveActorRow(row("cancelled")), null);
});

test("a request awaiting a cancellation decision shows no actor row", () => {
  assert.equal(leaveActorRow(row("cancellation_requested")), null);
});

// ── the whole rule ──────────────────────────────────────────────────────────

test("exactly three statuses produce a row, each with its own label", () => {
  const labels: Record<string, string | null> = {};
  for (const status of ALL_STATUSES) {
    labels[status] = leaveActorRow(row(status))?.label ?? null;
  }
  assert.deepEqual(labels, {
    pending: "Routed to",
    approved: "Approved by",
    rejected: "Rejected by",
    cancelled: null,
    cancellation_requested: null,
  });
});

test("the row is never labelled the generic 'By' used by the All-leave table", () => {
  // The table needs one heading for mixed rows; the detail page has the status
  // in hand and says which decision it was.
  for (const status of ALL_STATUSES) {
    assert.notEqual(leaveActorRow(row(status))?.label, "By");
  }
});

// ── 6./7. seeing an actor is not being allowed to act ───────────────────────

test("the request owner sees the routing row but still gets no Review card", () => {
  const ME = "emp-1";
  const own = { ...row("pending"), employee_id: ME };
  // Told who has it...
  assert.equal(leaveActorRow(own)?.label, "Routed to");
  // ...and still cannot act on it, even as an authorised reviewer.
  assert.equal(canReviewLeave(own, true, ME), false);
});

test("a reviewer looking at somebody else's pending request gets both", () => {
  const other = { ...row("pending"), employee_id: "emp-2" };
  assert.equal(leaveActorRow(other)?.label, "Routed to");
  assert.equal(canReviewLeave(other, true, "emp-1"), true);
});

test("a plain employee viewing a settled request still sees the actor", () => {
  // Informational, not gated on review authority.
  const settled = { ...row("approved"), employee_id: "emp-1" };
  assert.equal(leaveActorRow(settled)?.name, APPROVER);
  assert.equal(canReviewLeave(settled, false, "emp-1"), false);
});
