/**
 * Leave queue tab-badge counts (see types.ts).
 *
 * The badge and the list it labels have to describe ONE dataset. They drifted
 * because the two count call sites in `leave-management-panel.tsx` simply left
 * `exclude_self` off while the queues below them passed it - so a Project Head
 * with a pending request of their own saw a tab reading "1" that opened on an
 * empty table. This repo has no DOM test runner by design, so these pin the
 * pure params helper both call sites now build from.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { leaveQueueCountParams } from "./types.ts";

test("a pending badge counts the same dataset the pending list shows", () => {
  // A Project Head's queue: their own request is filtered out of the list, so
  // it must be filtered out of the number on the tab too.
  assert.deepEqual(leaveQueueCountParams("pending", true), {
    status: "pending",
    limit: 1,
    offset: 0,
    exclude_self: true,
  });
});

test("a cancellation badge excludes self exactly like the pending one", () => {
  assert.deepEqual(leaveQueueCountParams("cancellation_requested", true), {
    status: "cancellation_requested",
    limit: 1,
    offset: 0,
    exclude_self: true,
  });
});

test("a PM's queues count everything, their own requests included", () => {
  // `excludeSelf` is false for the PM panel, which is the pre-existing scope
  // and must not change: this fix aligns the badge with the list, it does not
  // narrow what a PM sees.
  for (const status of ["pending", "cancellation_requested"] as const) {
    assert.deepEqual(leaveQueueCountParams(status, false), {
      status,
      limit: 1,
      offset: 0,
      exclude_self: false,
    });
  }
});

test("a badge never fetches rows, only the total", () => {
  for (const excludeSelf of [true, false]) {
    const params = leaveQueueCountParams("pending", excludeSelf);
    assert.equal(params.limit, 1);
    assert.equal(params.offset, 0);
  }
});

test("the badge and the list agree on exclude_self for both queues", () => {
  // The invariant the bug broke, stated directly: whatever flag the panel holds
  // reaches the count unchanged, so the two can never disagree again.
  for (const excludeSelf of [true, false]) {
    for (const status of ["pending", "cancellation_requested"] as const) {
      assert.equal(leaveQueueCountParams(status, excludeSelf).exclude_self, excludeSelf);
    }
  }
});
