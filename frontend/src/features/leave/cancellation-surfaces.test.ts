/**
 * Phase 4C - WHERE a cancellation is decided, and what the waiting row says.
 *
 * ONE CHANGE, AND IT IS A REMOVAL OF A DUPLICATE
 * ==============================================
 * Approve cancellation / Keep approved leave existed on two screens: the
 * Cancellation requests queue's Actions column, and the request's own detail
 * page. The queue is the one that stays. The detail page's whole "Cancellation
 * request" card is gone - buttons and explanatory text alike - and no fact went
 * with it: the ordinary Leave Request card still shows the Cancellation
 * Requested badge, the dates, the Type and the routing rows.
 *
 * EVERYTHING ELSE IS UNTOUCHED, and most of this file exists to prove it:
 *
 *   Leave Requests table   Cancel Request (pending), Request Cancellation
 *                          (approved and still ahead), and the waiting row's
 *                          neutral wording
 *   Leave Detail           the owner's own Withdraw / Request Cancellation card,
 *                          exactly as before - the removal above is the
 *                          REVIEWER's card, not this one
 *   Permission Detail      both its Withdraw cards and its own cancellation
 *                          review actions, exactly as before
 *   Cancellation queue     both reviewer buttons
 *
 * THE WORDING. The waiting row read "Awaiting PM review". A cancellation is
 * decided by the authorised Project Manager OR by the routed Project Head, so
 * naming a role told half the employees to wait on somebody who would never see
 * it. `LEAVE_CANCELLATION_AWAITING_LABEL` names nobody.
 *
 * The repo has no DOM test harness, so what a page RENDERS is asserted by
 * reading the component source - the pattern `permission-display.test.ts`
 * already uses - and what a rule DECIDES is asserted through the rule itself.
 * Comments are stripped first, so this file fails on a button that is rendered,
 * not on a sentence describing one that is not.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import {
  LEAVE_CANCELLATION_AWAITING_LABEL,
  canCancelLeave,
  canRequestLeaveCancellation,
  canReviewLeaveCancellation,
  leaveTypeLabel,
  type LeaveHalfDayPeriod,
  type LeaveRequest,
  type LeaveStatus,
} from "./types.ts";

const ME = "emp-1";
const SOMEONE_ELSE = "emp-2";
const TODAY = "2026-09-05";

function leave(over: Partial<LeaveRequest> = {}): LeaveRequest {
  return {
    id: "lr-1",
    employee_id: ME,
    employee_name: "Sowrish Kumar S",
    start_date: "2026-09-10",
    end_date: "2026-09-10",
    working_days: 1,
    classification: "normal",
    half_day_period: null,
    reason: "Personal",
    status: "approved",
    manager_id: null,
    manager_name: null,
    manager_comment: null,
    routed_project_id: null,
    routed_to_name: null,
    created_at: "2026-09-01T04:00:00Z",
    updated_at: "2026-09-01T04:00:00Z",
    ...over,
  };
}

const source = (relative: string) =>
  readFileSync(new URL(relative, import.meta.url), "utf8");

/** A component's source with its comments removed, so an assertion about what
 *  renders cannot be satisfied - or defeated - by prose. */
function code(relative: string): string {
  return source(relative)
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^[ \t]*\/\/.*$/gm, "");
}

const DETAIL = "./components/leave-detail.tsx";
const TABLE = "./components/leave-history.tsx";
const QUEUE = "./components/leave-cancellation-review-panel.tsx";
const PERMISSION_DETAIL = "../permissions/components/permission-detail.tsx";

// ---------- 1. the queue keeps the decision ---------------------------------

test("the Cancellation requests queue still offers both reviewer actions", () => {
  const queue = code(QUEUE);
  assert.ok(queue.includes("Approve cancellation"));
  assert.ok(queue.includes("Keep approved leave"));
  // Its permission half, and the mutations behind both, are untouched too - the
  // queue is where a withdrawal of either kind is decided.
  assert.ok(queue.includes("Keep approved permission"));
  assert.ok(queue.includes("useApproveLeaveCancellation"));
  assert.ok(queue.includes("useRejectLeaveCancellation"));
});

// ---------- 2. the detail page no longer duplicates it ----------------------

test("the detail page carries no cancellation-request card at all", () => {
  const detail = code(DETAIL);
  // The whole card is gone - heading, both sentences, and the two buttons that
  // duplicated the queue. Nothing partial survived.
  for (const gone of [
    "Approve cancellation",
    "Keep approved leave",
    "useApproveLeaveCancellation",
    "useRejectLeaveCancellation",
    "<CardTitle>Cancellation request</CardTitle>",
    "has asked to withdraw this approved",
    "Attendance is not changed automatically",
    "canReviewLeaveCancellation",
  ]) {
    assert.ok(!detail.includes(gone), `Leave Detail must not carry "${gone}"`);
  }
});

test("a withdrawn request still describes itself through the ordinary card", () => {
  // Removing the cancellation card removed no FACT. The Leave Request card
  // still carries the status badge - which reads Cancellation Requested - the
  // dates, the Type and the routing rows, for every status alike.
  const detail = code(DETAIL);
  assert.ok(detail.includes("<CardTitle>Leave Request</CardTitle>"));
  assert.ok(detail.includes("<LeaveStatusBadge status={leave.status} />"));
  assert.ok(detail.includes("leaveTypeLabel(leave)"));
  assert.ok(detail.includes("leaveActorRows"));
});

test("who may DECIDE a withdrawal did not change", () => {
  // Hiding a button was never authorisation, and this rule - which the queue
  // reads too - is exactly what it was. `service.py::_assert_can_review` is
  // still the thing that actually refuses a decision.
  const waiting = leave({
    status: "cancellation_requested",
    employee_id: SOMEONE_ELSE,
  });
  assert.equal(canReviewLeaveCancellation(waiting, true, ME), true);
  assert.equal(canReviewLeaveCancellation(waiting, false, ME), false);
  assert.equal(
    canReviewLeaveCancellation(leave({ status: "cancellation_requested" }), true, ME),
    false,
    "nobody decides the withdrawal of their own leave",
  );
});

// ---------- 3-5. the employee's own Request Cancellation, both surfaces -----

test("the Leave Requests table still offers Request Cancellation", () => {
  const table = code(TABLE);
  assert.ok(table.includes("Request Cancellation"));
  assert.ok(table.includes("canRequestLeaveCancellation"));
  assert.equal(canRequestLeaveCancellation(leave(), ME, TODAY), true);
});

test("Leave Detail still offers the owner's Withdraw card", () => {
  // RESTORED. An earlier pass removed this; it was never in scope. The card, its
  // button and the dialog it opens are all back exactly as they were.
  const detail = code(DETAIL);
  assert.ok(detail.includes("<CardTitle>Withdraw</CardTitle>"));
  assert.ok(detail.includes("Request Cancellation"));
  assert.ok(detail.includes("canRequestLeaveCancellation"));
  assert.ok(detail.includes("LeaveCancelDialog"));
});

test("a half day initiates a cancellation exactly as a full day does", () => {
  // No rule anywhere consults `half_day_period` for this - the ONLY special
  // half-day behaviour is the Type label and the 0.5 accounting, neither of
  // which is touched here.
  const halves: (LeaveHalfDayPeriod | null)[] = ["first_half", "second_half", null];
  for (const half of halves) {
    const req = leave({ half_day_period: half });
    assert.equal(canRequestLeaveCancellation(req, ME, TODAY), true);
    assert.equal(canCancelLeave({ ...req, status: "pending" }, ME), true);
    assert.equal(
      canReviewLeaveCancellation(
        { ...req, status: "cancellation_requested", employee_id: SOMEONE_ELSE },
        true,
        ME,
      ),
      true,
    );
  }
  assert.equal(
    leaveTypeLabel({ classification: "normal", half_day_period: "first_half" }),
    "Half Day (First)",
  );
  assert.equal(
    leaveTypeLabel({ classification: "normal", half_day_period: "second_half" }),
    "Half Day (Second)",
  );
});

// ---------- 6-8. the rest of the Action column ------------------------------

test("a pending request still offers Cancel Request", () => {
  const table = code(TABLE);
  assert.ok(table.includes("Cancel Request"));
  assert.equal(canCancelLeave(leave({ status: "pending" }), ME), true);
  assert.equal(canCancelLeave(leave({ status: "pending" }), SOMEONE_ELSE), false);
  assert.equal(canCancelLeave(leave({ status: "approved" }), ME), false);
});

test("a waiting withdrawal reads Awaiting for a review, and names nobody", () => {
  assert.equal(LEAVE_CANCELLATION_AWAITING_LABEL, "Awaiting for a review");
  assert.ok(
    code(TABLE).includes("{LEAVE_CANCELLATION_AWAITING_LABEL}"),
    "the Action column must render the shared label, not its own string",
  );
  // Either a Project Manager or the routed Project Head may rule, so the label
  // must not promise one of them.
  for (const role of ["PM", "Project Manager", "Head", "Manager"]) {
    assert.ok(
      !LEAVE_CANCELLATION_AWAITING_LABEL.includes(role),
      `the neutral label must not name "${role}"`,
    );
  }
});

test("the superseded wording is gone from the table entirely", () => {
  // Read WITH comments: the old string must not survive even as a leftover note.
  const table = source(TABLE);
  for (const gone of [
    "Awaiting PM review",
    "Awaiting Project Manager review",
    "Awaiting Head review",
  ]) {
    assert.ok(!table.includes(gone), `the superseded wording "${gone}" is back`);
  }
});

test("every other row of the table behaves as it did", () => {
  // Approved but finished: nothing left to withdraw.
  assert.equal(
    canRequestLeaveCancellation(leave({ end_date: "2026-09-04" }), ME, TODAY),
    false,
  );
  // Somebody else's approved leave is not the reader's to withdraw.
  assert.equal(canRequestLeaveCancellation(leave(), SOMEONE_ELSE, TODAY), false);
  // A settled request offers neither action, so its Action cell stays empty.
  for (const status of ["rejected", "cancelled"] as LeaveStatus[]) {
    const req = leave({ status });
    assert.equal(canCancelLeave(req, ME), false);
    assert.equal(canRequestLeaveCancellation(req, ME, TODAY), false);
  }
});

// ---------- permission cancellation UI is not collateral --------------------

test("Permission Detail keeps every cancellation control it had", () => {
  const detail = code(PERMISSION_DETAIL);
  // The pending withdrawal, the approved-permission ask, and the reviewer's own
  // panel. None of this was in scope; an earlier pass removed the middle one and
  // it is restored.
  for (const kept of [
    "canCancelPermission",
    "Cancel permission request",
    "canRequestPermissionCancellation",
    "useRequestPermissionCancellation",
    "Request cancellation",
    "CancellationReviewActions",
  ]) {
    assert.ok(detail.includes(kept), `Permission Detail must still carry "${kept}"`);
  }
});

// ---------- 9. no typography or layout was touched --------------------------

test("no styling was introduced on any surface this phase touched", () => {
  // The change was a deletion of two buttons and a wording swap. Nothing may
  // have grown an inline style, a font rule or a size override - the class
  // vocabulary of these files is the design system's and stays untouched.
  for (const file of [DETAIL, TABLE, QUEUE, PERMISSION_DETAIL]) {
    const text = source(file);
    for (const banned of ["style={{", "fontSize", "font-size", "font-family"]) {
      assert.ok(!text.includes(banned), `${file} must not carry "${banned}"`);
    }
  }
  // The surviving card's own typography, pinned exactly: the two paragraphs are
  // still the shared `text-sm text-muted-foreground`, in a `space-y-3` card body
  // built from the standard primitives.
  const detail = code(DETAIL);
  assert.ok(detail.includes('<CardContent className="space-y-3">'));
  assert.ok(detail.includes('<p className="text-sm text-muted-foreground">'));
});
