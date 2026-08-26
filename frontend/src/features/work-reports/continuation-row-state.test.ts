/**
 * Pure-logic tests for the ONE rule this correction turns on: a pending
 * lump-sum continuation blocks marking that ACTIVITY complete, and blocks
 * nothing else.
 *
 * The bug it pins: ticking "Mark task fully completed" on an activity whose
 * continuation was still awaiting the Project Head made the whole report save
 * fail, so a report carrying two ordinary activities and one pending
 * continuation could not be submitted at all. The editor now derives the row's
 * continuation state here and disables only that checkbox; the Submit button is
 * never touched by it.
 *
 * The editor reads a row's state from two places that must agree - the SAVED
 * status the API serves, and (for a row just attached in this editor, which has
 * no saved status yet) the open work item it continues. Both paths are pinned.
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit).
 * The backend enforces the same split independently - see backend
 * tests/test_ls_continuation_lifecycle.py, section 12.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  completionBlockedByContinuation,
  continuationRowStatus,
} from "./open-task-state.ts";
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
// what the state blocks - and what it must never block
// --------------------------------------------------------------------------
test("only a pending continuation holds up marking the activity complete", () => {
  assert.equal(completionBlockedByContinuation("pending"), true);
  assert.equal(completionBlockedByContinuation("approved"), false);
  assert.equal(completionBlockedByContinuation("rejected"), false);
  assert.equal(completionBlockedByContinuation(null), false);
});
