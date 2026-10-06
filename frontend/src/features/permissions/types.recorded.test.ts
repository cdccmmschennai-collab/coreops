/**
 * A permission a project manager RECORDED from Daily Attendance Review is not a
 * request the employee made and nobody approved it. These pin that every
 * surface says so - the badge, the detail card's vocabulary, the actor row and
 * the closing line - and that an employee-requested permission reads exactly as
 * it always has.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PERMISSION_STATUS_LABEL,
  PERMISSION_STATUS_VARIANT,
  canCancelPermission,
  canRequestPermissionCancellation,
  isManagerRecorded,
  permissionActorRows,
  permissionCancellationCell,
  permissionClosingMessage,
  permissionDetailWording,
  type PermissionStatus,
} from "./types.ts";

const ME = "emp-1";
const TODAY = "2026-10-06";
const PM = "Alex Manager";

const detail = (
  status: PermissionStatus,
  recorded_by_manager: boolean,
  extra: { routed_to_name?: string | null } = {},
) => ({
  status,
  recorded_by_manager,
  reviewer_name: PM,
  routed_to_name: extra.routed_to_name ?? null,
  employee_id: ME,
  permission_date: TODAY,
});

// ── badge ───────────────────────────────────────────────────────────────────

test("Recorded has its own label and the blue info badge, distinct from Approved", () => {
  assert.equal(PERMISSION_STATUS_LABEL.recorded, "Recorded");
  assert.equal(PERMISSION_STATUS_LABEL.approved, "Approved");
  assert.equal(PERMISSION_STATUS_VARIANT.recorded, "info");
  assert.equal(PERMISSION_STATUS_VARIANT.approved, "success");
  assert.notEqual(PERMISSION_STATUS_VARIANT.recorded, PERMISSION_STATUS_VARIANT.approved);
  assert.equal(PERMISSION_STATUS_VARIANT.cancelled, "neutral");
});

// ── origin ──────────────────────────────────────────────────────────────────

test("a recorded permission is manager-recorded, and stays so once cancelled", () => {
  assert.equal(isManagerRecorded(detail("recorded", true)), true);
  assert.equal(isManagerRecorded(detail("cancelled", true)), true);
});

test("the employee's closing line is replaced by the action, so it never says 'No further action'", () => {
  // The page renders `permissionClosingMessage` only when the reader has no
  // action; for the owning employee a recorded permission now has one.
  const d = detail("recorded", true);
  const hasAction = canRequestPermissionCancellation(d, ME, TODAY);
  assert.equal(hasAction, true);
});

test("an employee request is never manager-recorded, in any status", () => {
  for (const s of [
    "pending",
    "approved",
    "rejected",
    "cancelled",
    "cancellation_requested",
  ] as PermissionStatus[]) {
    assert.equal(isManagerRecorded(detail(s, false)), false, s);
  }
});

// ── detail page: manager-recorded ───────────────────────────────────────────

test("the recorded detail uses Recorded / Recorded by and no request or review fields", () => {
  const w = permissionDetailWording(detail("recorded", true));
  assert.equal(w.title, "Manager Recorded Permission");
  assert.equal(w.createdLabel, "Recorded");
  assert.equal(w.showReviewFields, false);
  assert.equal(w.beforeLabel, "Before recording");

  const rows = permissionActorRows(detail("recorded", true, { routed_to_name: "Someone" }));
  assert.deepEqual(rows, [{ label: "Recorded by", name: PM }]);
  const labels = rows.map((r) => r.label).join(" ");
  for (const banned of ["Approved by", "Routed to", "Requested", "Reviewed"]) {
    assert.ok(!labels.includes(banned), banned);
  }
});

test("the recorded detail explains itself", () => {
  assert.equal(
    permissionClosingMessage(detail("recorded", true)),
    "This permission was directly recorded by the manager. No further action is available.",
  );
});

test("a cancelled recorded permission keeps its manager-recorded vocabulary", () => {
  const d = detail("cancelled", true);
  assert.equal(permissionDetailWording(d).createdLabel, "Recorded");
  assert.deepEqual(permissionActorRows(d), [{ label: "Recorded by", name: PM }]);
  assert.equal(
    permissionClosingMessage(d),
    "This permission was recorded by the manager and is cancelled. No further action is available.",
  );
});

test("the employee may request cancellation of a recorded permission, as of an approved one", () => {
  const d = detail("recorded", true);
  // The existing request-cancellation action, never the one-step cancel.
  assert.equal(canRequestPermissionCancellation(d, ME, TODAY), true);
  assert.equal(canCancelPermission(d, ME), false);
  assert.equal(permissionCancellationCell(d, ME, TODAY), "request");
  // Same rules as approved: own permission only, not once its day has passed.
  assert.equal(canRequestPermissionCancellation(d, "emp-2", TODAY), false);
  assert.equal(
    canRequestPermissionCancellation({ ...d, permission_date: "2026-10-05" }, ME, TODAY),
    false,
  );
  // Unchanged for an approved request.
  assert.equal(canRequestPermissionCancellation(detail("approved", false), ME, TODAY), true);
});

test("a withdrawal pending on a recorded permission keeps its manager-recorded vocabulary", () => {
  const d = detail("cancellation_requested", true);
  assert.equal(isManagerRecorded(d), true);
  assert.equal(permissionDetailWording(d).createdLabel, "Recorded");
  assert.deepEqual(permissionActorRows(d), [{ label: "Recorded by", name: PM }]);
  assert.equal(permissionCancellationCell(d, ME, TODAY), "requested");
  // An approved request awaiting withdrawal reads exactly as before.
  const a = detail("cancellation_requested", false);
  assert.equal(isManagerRecorded(a), false);
  assert.equal(permissionDetailWording(a).title, "Permission Request");
  assert.deepEqual(permissionActorRows(a), []);
});

// ── detail page: employee-requested is unchanged ────────────────────────────

test("an approved request keeps Permission Request / Requested / Reviewed / Approved by", () => {
  const d = detail("approved", false, { routed_to_name: "Head Person" });
  const w = permissionDetailWording(d);
  assert.equal(w.title, "Permission Request");
  assert.equal(w.createdLabel, "Requested");
  assert.equal(w.showReviewFields, true);
  assert.equal(w.beforeLabel, "Before approval");
  assert.deepEqual(permissionActorRows(d), [
    { label: "Routed to", name: "Head Person" },
    { label: "Approved by", name: PM },
  ]);
  assert.equal(
    permissionClosingMessage(d),
    "This request is approved and no further action is available.",
  );
});

test("a cancelled employee request reads exactly as before", () => {
  const d = detail("cancelled", false);
  assert.equal(permissionDetailWording(d).title, "Permission Request");
  assert.deepEqual(permissionActorRows(d), []);
  assert.equal(
    permissionClosingMessage(d),
    "This request is cancelled and no further action is available.",
  );
});
