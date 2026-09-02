/**
 * Whether the leave detail page has a Review card at all (see `canReviewLeave`
 * in types.ts).
 *
 * It decides whether the Review card is mounted at all, and with it the Approve
 * / Reject buttons inside. False means no Review card in the DOM - not a
 * disabled one, not an explanatory one. It does NOT decide the layout: the
 * two-column desktop grid is unconditional, so Leave Request keeps the left half
 * either way and the right column is just empty when there is no reviewer.
 * There is no DOM test runner in this repo by design; the rendering itself stays
 * a manual check.
 *
 * It decides RENDERING ONLY. The backend refuses each of these cases
 * independently.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { canReviewLeave } from "./types.ts";
import type { LeaveStatus } from "./types.ts";

const ME = "emp-1";
const SOMEONE_ELSE = "emp-2";

const req = (status: LeaveStatus, employee_id = SOMEONE_ELSE) => ({
  status,
  employee_id,
});

const ALL_STATUSES: LeaveStatus[] = [
  "pending",
  "approved",
  "rejected",
  "cancelled",
  "cancellation_requested",
];

// `isReviewer` is the caller's already-resolved "PM, or the assigned Project
// Head for this request" answer - the page reads it from the role and the
// report scope, and this helper does not widen it.
const REVIEWER = true;
const NOT_A_REVIEWER = false;

// ── 1. an authorised reviewer, someone else's pending request ───────────────

test("a PM or Head reviewing another employee's pending request sees Review", () => {
  assert.equal(canReviewLeave(req("pending"), REVIEWER, ME), true);
});

// ── 2./3. never your own request, whoever you are ───────────────────────────

test("a Project Head viewing their OWN pending request gets no Review card", () => {
  assert.equal(canReviewLeave(req("pending", ME), REVIEWER, ME), false);
});

test("a Project Manager viewing their OWN pending request gets no Review card", () => {
  // Same rule, same code path: a PM and a Head are both employees who file
  // their own leave, and neither may approve it here.
  assert.equal(canReviewLeave(req("pending", ME), REVIEWER, ME), false);
});

// ── 4. an unauthorised viewer ───────────────────────────────────────────────

test("a normal employee gets no Review card, even on a pending request", () => {
  assert.equal(canReviewLeave(req("pending"), NOT_A_REVIEWER, ME), false);
});

test("an unauthorised viewer gets no Review card on any status", () => {
  for (const status of ALL_STATUSES) {
    assert.equal(canReviewLeave(req(status), NOT_A_REVIEWER, ME), false, status);
  }
});

// ── 5./6./7. settled requests are not actionable ────────────────────────────

test("an approved request has no Review card", () => {
  assert.equal(canReviewLeave(req("approved"), REVIEWER, ME), false);
});

test("a rejected request has no Review card", () => {
  assert.equal(canReviewLeave(req("rejected"), REVIEWER, ME), false);
});

test("a cancelled request has no Review card", () => {
  // The status is shown once, by the Leave Request panel - a Review card here
  // would only repeat it.
  assert.equal(canReviewLeave(req("cancelled"), REVIEWER, ME), false);
});

test("a cancellation request is not reviewed here either", () => {
  // Cancellations have their own queue and their own two mutations; this panel
  // must not offer plain Approve/Reject for one.
  assert.equal(canReviewLeave(req("cancellation_requested"), REVIEWER, ME), false);
});

test("pending is the ONLY reviewable status", () => {
  for (const status of ALL_STATUSES) {
    assert.equal(
      canReviewLeave(req(status), REVIEWER, ME),
      status === "pending",
      status,
    );
  }
});

// ── the whole rule, exhaustively ────────────────────────────────────────────

test("the only way to get a Review card is pending + reviewer + not your own", () => {
  // Every other combination leaves the grid's right column empty.
  for (const status of ALL_STATUSES) {
    for (const isReviewer of [REVIEWER, NOT_A_REVIEWER]) {
      for (const owner of [ME, SOMEONE_ELSE]) {
        const expected =
          status === "pending" && isReviewer && owner === SOMEONE_ELSE;
        assert.equal(
          canReviewLeave(req(status, owner), isReviewer, ME),
          expected,
          `${status} / reviewer=${isReviewer} / owner=${owner}`,
        );
      }
    }
  }
});

// ── an account with no linked employee ──────────────────────────────────────

test("an account with no linked employee still reviews others' requests", () => {
  assert.equal(canReviewLeave(req("pending"), REVIEWER, null), true);
  assert.equal(canReviewLeave(req("pending"), REVIEWER, undefined), true);
});
