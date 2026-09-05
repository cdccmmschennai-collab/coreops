/**
 * The leave CANCELLATION workflow, as the detail page and the queue decide it.
 *
 * THE GAP THIS PINS DOWN
 * ======================
 * A withdrawal of approved leave has always been decidable from the Cancellation
 * requests TABLE, and clicking a row there has always opened Leave Detail - which
 * then offered nothing to do with it. The permission half of the same queue could
 * already be decided from its own detail page, so the two kinds of withdrawal
 * behaved differently for no reason a reader could see.
 *
 * `canReviewLeaveCancellation` is now that decision, made once and shaped exactly
 * like `canReviewPermissionCancellation`; `leaveReturnLabel` is what stops the
 * back link on such a page claiming to lead to Leave Requests. Both are pure and
 * asserted here rather than once per component - the repo has no DOM test runner,
 * and the way a rule is made testable is to keep it out of the JSX.
 *
 * STILL OUT OF SCOPE (Phase 3): no `half_day` attendance row, no
 * `leave_day_fraction`, no balance movement. A cancellation carries the half
 * through so it can be NAMED correctly; nothing here prices anything.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";
import {
  LEAVE_LIST_HREF,
  canRequestLeaveCancellation,
  canReviewLeave,
  canReviewLeaveCancellation,
  leaveReturnHref,
  leaveReturnLabel,
  leaveTypeLabel,
  type LeaveHalfDayPeriod,
  type LeaveRequest,
  type LeaveStatus,
} from "./types.ts";
import { allRequestTypeLabel, type AllRequest } from "./all-requests.ts";
import {
  canRequestPermissionCancellation,
  canReviewPermissionCancellation,
} from "../permissions/types.ts";

const ME = "emp-1";
const SOMEONE_ELSE = "emp-2";

/** The fields every rule below reads, and nothing else. */
function leave(over: Partial<LeaveRequest> = {}): LeaveRequest {
  return {
    id: "lr-1",
    employee_id: SOMEONE_ELSE,
    employee_name: "Sowrish Kumar S",
    start_date: "2027-03-03",
    end_date: "2027-03-03",
    working_days: 1,
    classification: "normal",
    half_day_period: null,
    reason: "Personal",
    status: "cancellation_requested",
    manager_id: null,
    manager_name: null,
    manager_comment: null,
    routed_project_id: null,
    routed_to_name: null,
    created_at: "2027-02-20T04:00:00Z",
    updated_at: "2027-02-20T04:00:00Z",
    ...over,
  };
}

/** The Cancellation requests queue's own address, as the table writes it into
 *  `?from` - `window.location.pathname + search` of the tab it was clicked on. */
const CANCELLATION_QUEUE = "/attendance?tab=leave&queue=cancellation";
const PENDING_QUEUE = "/attendance?tab=leave&queue=pending";

// ---------- 6-8. the half survives the withdrawal, and is what is NAMED -------

test("a half-day cancellation is identified as Half Day (First)/(Second)", () => {
  // THE CENTRAL ASSERTION of the display half. A half-day request classifies
  // Normal - one working day is <= 3 - and asking for it back does not change
  // that, so a Type cell reading `classification` alone would call a withdrawn
  // half day "Normal" in the queue and on the page that decides it.
  for (const period of ["first_half", "second_half"] as const) {
    const req = leave({ half_day_period: period, status: "cancellation_requested" });
    assert.equal(
      leaveTypeLabel(req),
      period === "first_half" ? "Half Day (First)" : "Half Day (Second)",
    );
    assert.notEqual(leaveTypeLabel(req), "Normal");
  }
});

test("the half is named the same way in every cancellation status", () => {
  // The label must not depend on where in the withdrawal the request has got to:
  // approved (about to be asked back), awaiting a decision, and cancelled all
  // describe the same absence the employee filed.
  const statuses: LeaveStatus[] = ["approved", "cancellation_requested", "cancelled"];
  for (const status of statuses) {
    assert.equal(
      leaveTypeLabel(leave({ status, half_day_period: "first_half" })),
      "Half Day (First)",
    );
  }
});

test("the Cancellation requests row prefixes the kind and keeps the half", () => {
  // What `leave-cancellation-review-panel.tsx::toLeaveRow` composes for its Type
  // cell, asserted through the same composer it calls: the queue holds both
  // kinds, so the leave half says which kind it is AND which leave it is.
  for (const period of ["first_half", "second_half"] as const) {
    const req = leave({ half_day_period: period });
    assert.equal(
      `Leave - ${leaveTypeLabel(req)}`,
      period === "first_half" ? "Leave - Half Day (First)" : "Leave - Half Day (Second)",
    );
  }
});

test("a half-day row of the mixed All Requests table is not Normal either", () => {
  // The same precedence through the other table that lists a withdrawn request,
  // so the two cannot disagree about what the reader is looking at.
  const half: LeaveHalfDayPeriod = "second_half";
  const row: AllRequest = {
    id: "lr-1",
    kind: "leave",
    employee_id: SOMEONE_ELSE,
    employee_name: "Sowrish Kumar S",
    from_date: "2027-03-03",
    to_date: "2027-03-03",
    status: "cancellation_requested",
    reason: "Personal",
    manager_id: null,
    manager_name: null,
    created_at: "2027-02-20T04:00:00Z",
    classification: "normal",
    working_days: 1,
    half_day_period: half,
    period: null,
    duration_hours: null,
  };
  assert.equal(allRequestTypeLabel(row), "Half Day (Second)");
});

// ---------- 11-13. who may decide a withdrawal -------------------------------

test("an authorised reviewer may approve or reject a waiting cancellation", () => {
  assert.equal(canReviewLeaveCancellation(leave(), true, ME), true);
});

test("a half-day cancellation is decidable by exactly the same rule", () => {
  // No case for the half anywhere in the rule: a half day is withdrawn by the
  // same person under the same state machine as a full day.
  for (const period of [null, "first_half", "second_half"] as const) {
    assert.equal(
      canReviewLeaveCancellation(leave({ half_day_period: period }), true, ME),
      true,
    );
  }
});

test("a non-reviewer gets no cancellation decision, whatever the status", () => {
  assert.equal(canReviewLeaveCancellation(leave(), false, ME), false);
  assert.equal(canReviewLeaveCancellation(leave(), false, null), false);
});

test("nobody decides the withdrawal of their own leave", () => {
  // A project manager and a Project Head are both employees who file their own
  // leave, half-day included. The backend's `_assert_can_review` refuses this
  // independently; hiding the card is never the only thing stopping it.
  assert.equal(
    canReviewLeaveCancellation(leave({ employee_id: ME }), true, ME),
    false,
  );
});

test("a request that is not awaiting a withdrawal decision offers none", () => {
  const settled: LeaveStatus[] = ["pending", "approved", "rejected", "cancelled"];
  for (const status of settled) {
    assert.equal(canReviewLeaveCancellation(leave({ status }), true, ME), false);
  }
});

test("the cancellation decision and the approve/reject decision never both show", () => {
  // Two different questions about two different statuses. A pending request is
  // reviewed; a withdrawal is decided; neither page state offers both cards.
  const pending = leave({ status: "pending" });
  assert.equal(canReviewLeave(pending, true, ME), true);
  assert.equal(canReviewLeaveCancellation(pending, true, ME), false);

  const withdrawing = leave({ status: "cancellation_requested" });
  assert.equal(canReviewLeave(withdrawing, true, ME), false);
  assert.equal(canReviewLeaveCancellation(withdrawing, true, ME), true);
});

// ---------- 4-7. who may ASK, for every kind of leave ------------------------

test("the owner may ask to withdraw approved leave of any type", () => {
  // Normal, Special and both halves - the ask is about the STATUS, not the type,
  // which is why there is no half-day branch to get wrong.
  const cases = [
    { classification: "normal", half_day_period: null },
    { classification: "special", half_day_period: null },
    { classification: "normal", half_day_period: "first_half" },
    { classification: "normal", half_day_period: "second_half" },
  ] as const;
  for (const shape of cases) {
    const req = leave({ ...shape, status: "approved", employee_id: ME });
    assert.equal(canRequestLeaveCancellation(req, ME, "2027-03-01"), true);
  }
});

test("only the owner may ask, and only while some of the leave is ahead", () => {
  const approved = leave({ status: "approved", employee_id: ME });
  assert.equal(canRequestLeaveCancellation(approved, SOMEONE_ELSE, "2027-03-01"), false);
  // Its last day has passed - a finished absence has nothing left to withdraw.
  assert.equal(canRequestLeaveCancellation(approved, ME, "2027-03-04"), false);
  // The last day itself still counts.
  assert.equal(canRequestLeaveCancellation(approved, ME, "2027-03-03"), true);
});

test("un-approved leave is not withdrawn by request - it is cancelled outright", () => {
  for (const status of ["pending", "rejected", "cancelled"] as const) {
    assert.equal(
      canRequestLeaveCancellation(
        leave({ status, employee_id: ME }),
        ME,
        "2027-03-01",
      ),
      false,
    );
  }
});

// ---------- 14. where a decision returns the reviewer to --------------------

test("deciding out of Cancellation requests returns to Cancellation requests", () => {
  // The panel's `onDone` pushes this exact href, which is also what the back
  // link uses - one `?from`, so the two cannot send the reader to two places.
  assert.equal(leaveReturnHref(CANCELLATION_QUEUE), CANCELLATION_QUEUE);
  assert.equal(leaveReturnLabel(CANCELLATION_QUEUE), "← Cancellation Requests");
});

test("the back link names the cancellation queue rather than Leave Requests", () => {
  // The reported problem: a cancellation reviewer must not be pointed at an
  // unrelated Leave Requests tab.
  assert.notEqual(leaveReturnLabel(CANCELLATION_QUEUE), "← Leave Requests");
});

test("the queue's own filters and page survive the round trip", () => {
  const withState =
    "/attendance?tab=leave&queue=cancellation&view=team&lh_offset=20";
  assert.equal(leaveReturnHref(withState), withState);
  assert.equal(leaveReturnLabel(withState), "← Cancellation Requests");
});

test("every other queue keeps the label it has always had", () => {
  assert.equal(leaveReturnLabel(PENDING_QUEUE), "← Leave Requests");
  assert.equal(leaveReturnLabel("/attendance?tab=leave&queue=all"), "← Leave Requests");
  assert.equal(leaveReturnLabel("/attendance?tab=leave"), "← Leave Requests");
  // A page opened cold - a notification, a bookmark, an email link.
  assert.equal(leaveReturnLabel(null), "← Leave Requests");
  assert.equal(leaveReturnHref(null), LEAVE_LIST_HREF);
});

test("a rejected `from` cannot name a destination it was denied", () => {
  // `leaveReturnHref` refuses anything but the Attendance page, so the label is
  // read off the RESOLVED href - a forwarded or hand-edited URL claiming the
  // cancellation queue elsewhere falls back to both the plain list and its label.
  for (const hostile of [
    "https://evil.example/attendance?queue=cancellation",
    "//evil.example/attendance?queue=cancellation",
    "/attendance-x?queue=cancellation",
    "/projects?queue=cancellation",
  ]) {
    assert.equal(leaveReturnHref(hostile), LEAVE_LIST_HREF);
    assert.equal(leaveReturnLabel(hostile), "← Leave Requests");
  }
});

// ---------- 15-17. what deliberately did NOT move ---------------------------

test("the permission cancellation rule is untouched and still the model", () => {
  // Requirement 15. The leave rule was shaped to match this one; asserting them
  // side by side is what stops the copy drifting into a second system.
  const permission = {
    status: "cancellation_requested" as const,
    employee_id: SOMEONE_ELSE,
  };
  assert.equal(canReviewPermissionCancellation(permission, true, ME), true);
  assert.equal(canReviewPermissionCancellation(permission, false, ME), false);
  assert.equal(
    canReviewPermissionCancellation({ ...permission, employee_id: ME }, true, ME),
    false,
  );
  assert.equal(
    canReviewPermissionCancellation({ ...permission, status: "approved" }, true, ME),
    false,
  );
  assert.equal(
    canRequestPermissionCancellation(
      { status: "approved", employee_id: ME, permission_date: "2027-03-03" },
      ME,
      "2027-03-01",
    ),
    true,
  );
});

test("the leave rule answers exactly as the permission rule does", () => {
  for (const status of [
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "cancellation_requested",
  ] as const) {
    for (const isReviewer of [true, false]) {
      for (const owner of [ME, SOMEONE_ELSE]) {
        assert.equal(
          canReviewLeaveCancellation(
            leave({ status, employee_id: owner }),
            isReviewer,
            ME,
          ),
          canReviewPermissionCancellation(
            { status, employee_id: owner },
            isReviewer,
            ME,
          ),
          `${status}/${isReviewer}/${owner}`,
        );
      }
    }
  }
});

test("full-day cancellation display is unchanged", () => {
  // Requirements 16 and 17: Normal and Special still come from the existing
  // classification system whenever there is no half on the row.
  assert.equal(leaveTypeLabel(leave({ classification: "normal" })), "Normal");
  assert.equal(leaveTypeLabel(leave({ classification: "special" })), "Special");
  assert.equal(
    `Leave - ${leaveTypeLabel(leave({ classification: "special" }))}`,
    "Leave - Special",
  );
});
