/**
 * Pure-logic tests for a row's lump-sum continuation state - which is a LABEL
 * and nothing more.
 *
 * A pending continuation gates nothing: not the completion checkbox, not the
 * save, not the submit. An employee who finishes an over-allowance lump-sum
 * activity on the continuation day ticks "Mark task fully completed" and submits
 * exactly as on any other day, and the Project Head's decision then settles
 * whether that work is accepted. This file exists to keep a gate from growing
 * back: there is no `completionBlockedByContinuation` any more, so a row's
 * status can only decide what the row SAYS.
 *
 * What it says is pinned here too - the two lines and no more, so the four
 * caveats the pending banner used to carry cannot creep back in.
 *
 * The editor reads a row's state from two places that must agree - the SAVED
 * status the API serves, and (for a row just attached in this editor, which has
 * no saved status yet) the open work item it continues. Both paths are pinned.
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit).
 * The backend enforces the same rule independently - see backend
 * tests/test_ls_continuation_lifecycle.py, section 3.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CONTINUATION_PENDING_DETAIL,
  CONTINUATION_PENDING_TITLE,
  continuationRowStatus,
} from "./open-task-state.ts";
import * as openTaskState from "./open-task-state.ts";
import type { OpenTask } from "./types.ts";

/** An open lump-sum work item with `used` work days already spent. */
function lumpsum(
  used: number,
  target: number,
  continuation_status: string | null = null,
): OpenTask {
  return {
    work_item_id: "wi-1",
    project_id: "p-1",
    sub_activity_id: "s-1",
    started_on: "2026-08-24",
    due_date: "2026-08-24",
    target_days: target,
    days_used: used,
    is_lumpsum: true,
    lifecycle: "OVERDUE",
    days_overdue: 0,
    requires_continuation_approval: continuation_status !== "approved",
    continuation_status,
    continuation_request_id: null,
    continuation_routed_to: null,
  } as unknown as OpenTask;
}

// --------------------------------------------------------------------------
// a SAVED row: the API's status is the answer, whatever the open list says
// --------------------------------------------------------------------------
test("a saved pending row is pending", () => {
  assert.equal(continuationRowStatus("pending"), "pending");
});

test("a saved approved row is approved", () => {
  assert.equal(continuationRowStatus("approved"), "approved");
});

test("a saved row with no approval involved has no status", () => {
  assert.equal(continuationRowStatus(null), null);
  assert.equal(continuationRowStatus(undefined), null);
});

// --------------------------------------------------------------------------
// an UNSAVED continuation: the state it is about to have on save
// --------------------------------------------------------------------------
test("continuing a lump-sum still inside its allowance needs no approval", () => {
  assert.equal(continuationRowStatus(null, lumpsum(1, 3)), null);
});

test("the last allowed work day still needs no approval", () => {
  assert.equal(continuationRowStatus(null, lumpsum(1, 2)), null);
});

test("past the allowance with no request yet reads as pending", () => {
  // Saving this row raises the request, so the editor says so up front rather
  // than letting the employee discover it after submitting.
  assert.equal(continuationRowStatus(null, lumpsum(2, 2)), "pending");
});

test("past the allowance with a pending request reads as pending", () => {
  assert.equal(continuationRowStatus(null, lumpsum(3, 1, "pending")), "pending");
});

test("an approved continuation reads as approved", () => {
  assert.equal(continuationRowStatus(null, lumpsum(3, 1, "approved")), "approved");
});

test("a rejected continuation reads as rejected", () => {
  assert.equal(continuationRowStatus(null, lumpsum(3, 1, "rejected")), "rejected");
});

test("a blank benchmark period still grants one work day", () => {
  // Mirrors the backend's max(1, target_days) clamp.
  assert.equal(continuationRowStatus(null, lumpsum(0, 0)), null);
  assert.equal(continuationRowStatus(null, lumpsum(1, 0)), "pending");
});

test("a non-lump-sum open task is never gated", () => {
  const quantity = { ...lumpsum(9, 1), is_lumpsum: false } as OpenTask;
  assert.equal(continuationRowStatus(null, quantity), null);
});

test("no open task and no saved status means no approval state", () => {
  assert.equal(continuationRowStatus(null, undefined), null);
  assert.equal(continuationRowStatus(null, null), null);
});

// --------------------------------------------------------------------------
// what the state blocks: nothing
// --------------------------------------------------------------------------
test("no continuation state gates anything - the helper that did is gone", () => {
  // The editor cannot disable the completion checkbox from a row's status if
  // there is no predicate to disable it by. Pinning the absence is what keeps
  // "pending therefore blocked" from being reintroduced.
  assert.equal(
    "completionBlockedByContinuation" in openTaskState,
    false,
    "a pending continuation must not gate completion, save or submit",
  );
});

// --------------------------------------------------------------------------
// what a pending row SAYS - two lines, no caveats
// --------------------------------------------------------------------------
test("the pending banner is exactly the two lines", () => {
  assert.equal(CONTINUATION_PENDING_TITLE, "Continuation requested");
  assert.equal(CONTINUATION_PENDING_DETAIL, "Awaiting Project Head approval.");
});

test("the pending copy claims nothing is blocked", () => {
  const copy = `${CONTINUATION_PENDING_TITLE} ${CONTINUATION_PENDING_DETAIL}`.toLowerCase();
  for (const claim of ["complete", "submit", "recorded work", "removed", "cannot"]) {
    assert.equal(copy.includes(claim), false, `pending copy still says "${claim}"`);
  }
});
