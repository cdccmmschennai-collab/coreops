/**
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { PM_APPROVAL_REQUIRED_LABEL, reworkRowBadge } from "./rework-approval.ts";

test("normal row before or after submit shows nothing", () => {
  assert.equal(reworkRowBadge(false, null), null);
  assert.equal(reworkRowBadge(false, undefined), null);
});

test("configured row before submit says PM approval is required", () => {
  assert.deepEqual(reworkRowBadge(true, null), {
    label: PM_APPROVAL_REQUIRED_LABEL,
    tone: "warning",
  });
});

test("submitted states come from the server status", () => {
  assert.equal(reworkRowBadge(true, "pending")?.label, "In Review");
  assert.equal(reworkRowBadge(true, "approved")?.tone, "success");
  assert.equal(reworkRowBadge(true, "rejected")?.label, "Rejected - Action Required");
  // Status wins even if the config was removed after submit.
  assert.equal(reworkRowBadge(false, "pending")?.label, "In Review");
});

test("a cancelled cycle falls back to the configuration", () => {
  assert.equal(reworkRowBadge(true, "cancelled")?.label, PM_APPROVAL_REQUIRED_LABEL);
  assert.equal(reworkRowBadge(false, "cancelled"), null);
});
