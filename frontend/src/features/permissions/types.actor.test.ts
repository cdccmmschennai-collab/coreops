/**
 * "Routed to" and "Approved by" / "Rejected by" are two different facts.
 *
 * `permissionActorRows` is what Permission Detail shows under Status, and a
 * settled request shows BOTH rows:
 *
 *   pending    Routed to
 *   approved   Routed to  +  Approved by
 *   rejected   Routed to  +  Rejected by
 *
 * The rule these tests exist to protect is that neither is ever derived from the
 * other: a pending request must not borrow the routed recipient's name to look
 * decided, and a decided request must not have its actor recomputed from the
 * routing - the person a request was sent to and the person who ruled on it are
 * frequently different people, and both must survive to the page intact.
 *
 * The labels are Leave's labels; "Reviewed by" no longer exists here.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  permissionActorRows,
  permissionDecisionActor,
  type PermissionActorRow,
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

function labels(rows: PermissionActorRow[]): string[] {
  return rows.map((r) => r.label);
}

function nameFor(rows: PermissionActorRow[], label: string): string | null {
  return rows.find((r) => r.label === label)?.name ?? null;
}

// ── pending: routed to, and no decision ─────────────────────────────────────

test("a pending request names who it is routed to", () => {
  assert.deepEqual(
    permissionActorRows(detail({ status: "pending", reviewer_name: null })),
    [{ label: "Routed to", name: "Nainar B" }],
  );
});

test("a pending request shows no Approved by", () => {
  // Defensive: nothing should stamp a reviewer on a pending row, but if a stale
  // one arrived the page must not invent a decision that has not happened.
  assert.deepEqual(labels(permissionActorRows(detail({ status: "pending" }))), [
    "Routed to",
  ]);
});

test("a pending request shows no Rejected by", () => {
  assert.equal(
    nameFor(permissionActorRows(detail({ status: "pending" })), "Rejected by"),
    null,
  );
});

test("an unroutable pending request shows no row rather than a blank one", () => {
  assert.deepEqual(
    permissionActorRows(detail({ status: "pending", routed_to_name: null })),
    [],
  );
});

// ── approved: routing AND the actual approver, side by side ─────────────────

test("an approved request keeps Routed to visible", () => {
  assert.equal(
    nameFor(permissionActorRows(detail()), "Routed to"),
    "Nainar B",
  );
});

test("an approved request is Approved by the person who decided it", () => {
  assert.deepEqual(permissionActorRows(detail()), [
    { label: "Routed to", name: "Nainar B" },
    { label: "Approved by", name: "Priya Ramesh" },
  ]);
});

test("the approver is the actual actor, never the routed recipient", () => {
  assert.equal(nameFor(permissionActorRows(detail()), "Approved by"), "Priya Ramesh");
});

test("an approved request shows no Rejected by", () => {
  assert.equal(nameFor(permissionActorRows(detail()), "Rejected by"), null);
});

// ── rejected: the same two rows ─────────────────────────────────────────────

test("a rejected request keeps Routed to visible", () => {
  assert.equal(
    nameFor(permissionActorRows(detail({ status: "rejected" })), "Routed to"),
    "Nainar B",
  );
});

test("a rejected request is Rejected by the person who decided it", () => {
  assert.deepEqual(permissionActorRows(detail({ status: "rejected" })), [
    { label: "Routed to", name: "Nainar B" },
    { label: "Rejected by", name: "Priya Ramesh" },
  ]);
});

test("the rejector is the actual actor, never the routed recipient", () => {
  assert.equal(
    nameFor(permissionActorRows(detail({ status: "rejected" })), "Rejected by"),
    "Priya Ramesh",
  );
});

test("a rejected request shows no Approved by", () => {
  assert.equal(
    nameFor(permissionActorRows(detail({ status: "rejected" })), "Approved by"),
    null,
  );
});

// ── the decision actor and the routed recipient are independent ─────────────

test("the decision actor may differ from the routed recipient", () => {
  for (const status of ["approved", "rejected"] as const) {
    const rows = permissionActorRows(detail({ status }));
    assert.equal(rows.length, 2);
    assert.notEqual(rows[0].name, rows[1].name);
  }
});

test("neither row is derived from the other's data", () => {
  // Change the routing alone: the decision actor must not move with it.
  const rows = permissionActorRows(detail({ routed_to_name: "Someone Else" }));
  assert.deepEqual(rows, [
    { label: "Routed to", name: "Someone Else" },
    { label: "Approved by", name: "Priya Ramesh" },
  ]);
});

test("a decided request with no recorded actor still names its routing", () => {
  // A request decided before the actor was recorded, or one whose reviewer's
  // employee row has since gone. The missing half is dropped, never guessed.
  assert.deepEqual(permissionActorRows(detail({ reviewer_name: null })), [
    { label: "Routed to", name: "Nainar B" },
  ]);
  assert.deepEqual(permissionActorRows(detail({ reviewer_name: "  " })), [
    { label: "Routed to", name: "Nainar B" },
  ]);
});

test("a decided request with no recorded routing still names its actor", () => {
  assert.deepEqual(permissionActorRows(detail({ routed_to_name: null })), [
    { label: "Approved by", name: "Priya Ramesh" },
  ]);
});

// ── the two statuses that show nothing ──────────────────────────────────────

test("a cancelled request shows no actor row", () => {
  // `manager_id` on a cancelled row is its former APPROVER; the cancellation was
  // a different act, and no column records who performed it.
  assert.deepEqual(permissionActorRows(detail({ status: "cancelled" })), []);
});

test("a withdrawal awaiting a decision shows no actor row", () => {
  assert.deepEqual(
    permissionActorRows(detail({ status: "cancellation_requested" })),
    [],
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
    const rows = permissionActorRows(detail({ status }));
    const rowNamesTheActor = rows.some(
      (r) => r.label === "Approved by" || r.label === "Rejected by",
    );
    assert.equal(column !== null, rowNamesTheActor, `disagreement on "${status}"`);
  }
});
