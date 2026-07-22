/**
 * Pins the Benchmark Guide query-key contract.
 *
 * React Query invalidates by key PREFIX: invalidateQueries({ queryKey: A })
 * refreshes every query whose key starts with A. Every Activity Master mutation
 * hook (useCreate/Update/Deactivate Activity + Sub-Activity, and the access
 * mutations) invalidates activityMasterKeys.all. So the guide only refreshes on
 * those mutations if its key is a descendant of `all` — that is exactly what
 * this test guarantees, alongside stability and permission-awareness.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { activityMasterKeys } from "../activity-master/keys.ts";

function startsWith(key: readonly unknown[], prefix: readonly unknown[]): boolean {
  return prefix.every((seg, i) => key[i] === seg);
}

test("the guide key is a descendant of activityMasterKeys.all", () => {
  // -> an Activity Master mutation that invalidates `all` also refreshes it.
  const key = activityMasterKeys.benchmarkGuide("employee:emp-1");
  assert.ok(startsWith(key, activityMasterKeys.all));
});

test("the guide key is stable for a fixed scope", () => {
  assert.deepEqual(
    activityMasterKeys.benchmarkGuide("employee:emp-1"),
    activityMasterKeys.benchmarkGuide("employee:emp-1"),
  );
});

test("the guide key is permission-aware: a different scope is a different key", () => {
  assert.notDeepEqual(
    activityMasterKeys.benchmarkGuide("employee:emp-1"),
    activityMasterKeys.benchmarkGuide("project_manager:emp-2"),
  );
});
