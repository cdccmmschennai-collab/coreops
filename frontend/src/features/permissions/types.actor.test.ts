/**
 * Phase 4F - "Routed to" and "Reviewed by" are two different facts.
 *
 * `permissionActorRow` is the ONE row Permission Detail shows under Status, and
 * which question it answers depends on the status:
 *
 *   pending    Routed to     who is holding this request right now
 *   approved   Reviewed by   who granted it
 *   rejected   Reviewed by   who refused it
 *
 * The rule these tests exist to protect is that neither is ever derived from the
 * other: a pending request must not borrow the routed recipient's name to look
 * decided, and a decided request must not have its reviewer recomputed from the
 * current routing, which can have changed since.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  permissionActorRow,
  permissionDecisionActor,
  type PermissionRequestDetail,
} from "./types.ts";

type ActorFields = Pick<
  PermissionRequestDetail,
  "status" | "reviewer_name" | "routed_to_name"
>;

/** Routed to one person, decided by ANOTHER - so any implementation that
 *  answered one question with the other's data is visibly wrong. */
function detail(over: Partial<ActorFields> = {}): ActorFields {
  return {
    status: "approved",
    reviewer_name: "Priya Ramesh",
    routed_to_name: "Nainar B",
    ...over,
  };
}

// ── pending: routed to, and no reviewer ─────────────────────────────────────

test("a pending request names who it is routed to", () => {
  assert.deepEqual(
    permissionActorRow(detail({ status: "pending", reviewer_name: null })),
    { label: "Routed to", name: "Nainar B" },
  );
});

test("a pending request never shows a reviewer, even if one is recorded", () => {
  // Defensive: nothing should stamp a reviewer on a pending row, but if a
  // stale one arrived the page must still say "Routed to", not invent a
  // decision that has not happened.
  const row = permissionActorRow(detail({ status: "pending" }));
  assert.equal(row?.label, "Routed to");
  assert.equal(row?.name, "Nainar B");
});

test("an unroutable pending request shows no row rather than a blank one", () => {
  assert.equal(
    permissionActorRow(detail({ status: "pending", routed_to_name: null })),
    null,
  );
});

// ── decided: the actual actor, never the routing ────────────────────────────

test("an approved request is Reviewed by the person who decided it", () => {
  assert.deepEqual(permissionActorRow(detail()), {
    label: "Reviewed by",
    name: "Priya Ramesh",
  });
});

test("a rejected request is Reviewed by the person who decided it", () => {
  assert.deepEqual(permissionActorRow(detail({ status: "rejected" })), {
    label: "Reviewed by",
    name: "Priya Ramesh",
  });
});

test("the reviewer is never the routed recipient", () => {
  for (const status of ["approved", "rejected"] as const) {
    assert.notEqual(permissionActorRow(detail({ status }))?.name, "Nainar B");
  }
});

test("a decided request drops the routing question entirely", () => {
  // The backend stops sending `routed_to_name` once a request is settled; the
  // page must not fall back to it if it ever arrived anyway.
  assert.deepEqual(
    permissionActorRow(detail({ status: "approved", routed_to_name: "Someone Else" })),
    { label: "Reviewed by", name: "Priya Ramesh" },
  );
});

test("a decided request with no recorded reviewer shows no row", () => {
  // A request decided before the actor was recorded, or one whose reviewer's
  // employee row has since gone. Null, never a guess.
  assert.equal(permissionActorRow(detail({ reviewer_name: null })), null);
  assert.equal(permissionActorRow(detail({ reviewer_name: "  " })), null);
});

// ── the two statuses that show nothing ──────────────────────────────────────

test("a cancelled request shows no actor row", () => {
  // `manager_id` on a cancelled row is its former APPROVER; the cancellation was
  // a different act, and no column records who performed it.
  assert.equal(permissionActorRow(detail({ status: "cancelled" })), null);
});

test("a withdrawal awaiting a decision shows no actor row", () => {
  assert.equal(
    permissionActorRow(detail({ status: "cancellation_requested" })),
    null,
  );
});

// ── the table column and the detail row agree ───────────────────────────────

test("the By column and the detail row settle on the same statuses", () => {
  const statuses = [
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "cancellation_requested",
  ] as const;
  for (const status of statuses) {
    const column = permissionDecisionActor({
      status,
      manager_name: "Priya Ramesh",
    });
    const row = permissionActorRow(detail({ status }));
    const rowNamesTheActor = row?.label === "Reviewed by";
    assert.equal(
      column !== null,
      rowNamesTheActor,
      `disagreement on "${status}"`,
    );
  }
});
