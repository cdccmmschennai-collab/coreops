/**
 * Phase 4F - the All Requests table's per-row decisions.
 *
 * Three rules decide what a mixed leave/permission table shows and where a row
 * goes, and all three are pure functions so they can be tested without a DOM
 * (there is no DOM test runner in this repo by design):
 *
 *   allRequestTypeLabel   the Type cell
 *   allRequestActor       the "By" cell
 *   allRequestDetailHref  which detail page the row opens, and how it gets back
 *
 * The round trip - row -> detail -> back to All Requests with its filters - is
 * the pair `allRequestDetailHref` / the owning feature's return helper, tested
 * here for BOTH kinds because a permission row is the new half.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allRequestActor,
  allRequestDetailHref,
  allRequestTypeLabel,
  type AllRequest,
} from "./all-requests.ts";
import { leaveReturnHref } from "./types.ts";
import {
  PERMISSION_HISTORY_PATH,
  permissionReturnHref,
} from "../permissions/types.ts";

const LEAVE_ID = "3f2a91c4-0000-4000-8000-000000000001";
const PERM_ID = "3f2a91c4-0000-4000-8000-000000000002";

/** The All Requests tab as the panel's own URL actually looks. */
const ALL_REQUESTS = "/attendance?tab=leave&queue=all";

function leaveRow(over: Partial<AllRequest> = {}): AllRequest {
  return {
    id: LEAVE_ID,
    kind: "leave",
    employee_id: "e1",
    employee_name: "Santhosh Kumar",
    from_date: "2027-03-02",
    to_date: "2027-03-03",
    status: "approved",
    reason: "Family",
    manager_id: "m1",
    manager_name: "Priya Ramesh",
    created_at: "2027-02-01T10:00:00Z",
    classification: "normal",
    working_days: 2,
    period: null,
    duration_hours: null,
    ...over,
  };
}

function permissionRow(over: Partial<AllRequest> = {}): AllRequest {
  return {
    id: PERM_ID,
    kind: "permission",
    employee_id: "e1",
    employee_name: "Santhosh Kumar",
    from_date: "2027-03-04",
    to_date: "2027-03-04",
    status: "approved",
    reason: "Bank",
    manager_id: "m1",
    manager_name: "Priya Ramesh",
    created_at: "2027-02-01T11:00:00Z",
    classification: null,
    working_days: null,
    period: "first_half_2h",
    duration_hours: 2,
    ...over,
  };
}

// ── the Type cell ───────────────────────────────────────────────────────────

test("a leave row's Type is unchanged from the old All-leave table", () => {
  assert.equal(allRequestTypeLabel(leaveRow()), "Normal");
  assert.equal(allRequestTypeLabel(leaveRow({ classification: "special" })), "Special");
});

test("a permission row names its kind and its selected option", () => {
  assert.equal(
    allRequestTypeLabel(permissionRow()),
    "Permission - 1st Half - 2 Hours",
  );
  assert.equal(
    allRequestTypeLabel(permissionRow({ period: "second_half_1h", duration_hours: 1 })),
    "Permission - 2nd Half - 1 Hour",
  );
});

test("the Type label uses plain ASCII hyphens, never an em or en dash", () => {
  const label = allRequestTypeLabel(permissionRow());
  assert.ok(!label.includes("—") && !label.includes("–"), label);
});

test("a permission filed before the period option existed falls back, not blank", () => {
  // No half on record and none that could be safely guessed - the row must
  // still say what it is.
  assert.equal(
    allRequestTypeLabel(permissionRow({ period: null, duration_hours: 1 })),
    "Permission - 1hr",
  );
});

// ── the "By" cell ───────────────────────────────────────────────────────────

test("an approved or rejected row of either kind names its actual actor", () => {
  for (const status of ["approved", "rejected"] as const) {
    assert.equal(allRequestActor(leaveRow({ status })), "Priya Ramesh");
    assert.equal(allRequestActor(permissionRow({ status })), "Priya Ramesh");
  }
});

test("a pending row of either kind has no actor", () => {
  // Nobody has decided, so nothing may be shown - and in particular the routed
  // recipient's name must not be borrowed to fill the cell.
  assert.equal(
    allRequestActor(leaveRow({ status: "pending", manager_id: null, manager_name: null })),
    null,
  );
  assert.equal(
    allRequestActor(
      permissionRow({ status: "pending", manager_id: null, manager_name: null }),
    ),
    null,
  );
});

test("a cancelled row is blank even though the row still carries its approver", () => {
  // The record is deliberately kept server-side - a permission that was approved
  // and then withdrawn keeps its approver - but the cancellation was a different
  // act by a possibly different person, which nothing stores. Naming the
  // approver here would name the wrong actor.
  assert.equal(allRequestActor(leaveRow({ status: "cancelled" })), null);
  assert.equal(allRequestActor(permissionRow({ status: "cancelled" })), null);
});

test("a withdrawal awaiting a decision shows no actor either", () => {
  const status = "cancellation_requested" as const;
  assert.equal(allRequestActor(leaveRow({ status })), null);
  assert.equal(allRequestActor(permissionRow({ status })), null);
});

test("an actor whose name never resolved is a dash, not an empty cell", () => {
  assert.equal(allRequestActor(leaveRow({ manager_name: null })), null);
  assert.equal(allRequestActor(permissionRow({ manager_name: "   " })), null);
});

// ── which detail page a row opens ───────────────────────────────────────────

test("a leave row still opens the existing Leave Detail page", () => {
  assert.ok(
    allRequestDetailHref(leaveRow(), ALL_REQUESTS).startsWith(
      `/attendance/leave/${LEAVE_ID}?`,
    ),
  );
});

test("a permission row opens the existing Permission Detail page", () => {
  assert.ok(
    allRequestDetailHref(permissionRow(), ALL_REQUESTS).startsWith(
      `${PERMISSION_HISTORY_PATH}/${PERM_ID}?`,
    ),
  );
});

test("both kinds carry the All Requests address they were clicked from", () => {
  const encoded = encodeURIComponent(ALL_REQUESTS);
  assert.equal(
    allRequestDetailHref(leaveRow(), ALL_REQUESTS),
    `/attendance/leave/${LEAVE_ID}?from=${encoded}`,
  );
  assert.equal(
    allRequestDetailHref(permissionRow(), ALL_REQUESTS),
    `${PERMISSION_HISTORY_PATH}/${PERM_ID}?from=${encoded}`,
  );
});

// ── back to All Requests, filters and all ───────────────────────────────────

function roundTrip(row: AllRequest, from: string): string {
  const detail = allRequestDetailHref(row, from);
  const back = new URL(detail, "https://x").searchParams.get("from");
  return row.kind === "leave" ? leaveReturnHref(back) : permissionReturnHref(back);
}

test("both kinds come back to All Requests, not to a default list", () => {
  assert.equal(roundTrip(leaveRow(), ALL_REQUESTS), ALL_REQUESTS);
  assert.equal(roundTrip(permissionRow(), ALL_REQUESTS), ALL_REQUESTS);
});

test("the status filter, the date window and the page all survive the trip", () => {
  // Nothing in either helper names these parameters - the address is
  // round-tripped whole, which is why a filter added later needs no change here.
  const url =
    "/attendance?tab=leave&queue=all&ls=approved&lf=2027-03-01&lt=2027-03-31&lo=20";
  assert.equal(roundTrip(leaveRow(), url), url);
  assert.equal(roundTrip(permissionRow(), url), url);
});

test("a Project Head's Team-approvals All Requests tab comes back to itself", () => {
  const url = "/attendance?tab=leave&view=team&queue=all&ls=rejected";
  assert.equal(roundTrip(leaveRow(), url), url);
  assert.equal(roundTrip(permissionRow(), url), url);
});

// ── a permission page reached without a list behind it ──────────────────────

test("a cold-opened permission detail page still falls back to Permission History", () => {
  // A notification, an email link or a bookmark carries no `from` at all - which
  // is exactly what this link did before Phase 4F.
  assert.equal(
    allRequestDetailHref(permissionRow()),
    `${PERMISSION_HISTORY_PATH}/${PERM_ID}`,
  );
  assert.equal(permissionReturnHref(null), PERMISSION_HISTORY_PATH);
});

test("the employee's own Permission History still round-trips to itself", () => {
  assert.equal(
    roundTrip(permissionRow(), PERMISSION_HISTORY_PATH),
    PERMISSION_HISTORY_PATH,
  );
});

test("a forged permission return address is refused", () => {
  // `from` is a convenience the app writes for itself, never a destination a
  // hand-edited or forwarded URL gets to choose.
  for (const forged of [
    "https://evil.example/x",
    "//evil.example",
    "/attendance-x?a=1",
    "/attendance/permission-x",
  ]) {
    assert.equal(permissionReturnHref(forged), PERMISSION_HISTORY_PATH);
  }
});
