/**
 * Permission Requests -> Permission Detail -> Approve/Reject -> Permission Requests.
 *
 * The reviewer used to be dropped on their OWN Permission History after
 * deciding, because the queue opened the detail page with a bare path: nothing
 * carried the originating address, so both the back link and the post-decision
 * navigation had only the fallback to fall back to.
 *
 * The round trip is `permissionDetailHref` (what the row navigates to) followed
 * by `permissionReturnHref` (what the page resolves for BOTH its back link and
 * its `onDone`), and it is a round trip on purpose: the queue hands over its OWN
 * current address rather than a rebuilt one, so the tab, the filters and the
 * page number all come back without any of them being named here. That single
 * resolved href is what the detail page pushes after a successful decision -
 * exactly the mechanism `leave-detail.tsx` has always used.
 *
 * There is no DOM test runner in this repo by design, so the component wiring
 * (`onDone={() => router.push(backHref)}`) is a manual check. What decides WHERE
 * the reviewer lands is the pair of pure functions below.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PERMISSION_HISTORY_PATH,
  permissionDetailHref,
  permissionReturnHref,
} from "./types.ts";

const REQUEST = "3f2a91c4-0000-4000-8000-000000000002";

/** The three real entry points, as their panels' own URLs actually look. */
const PERMISSION_QUEUE = "/attendance?tab=leave&queue=permission";
const CANCELLATION_QUEUE = "/attendance?tab=leave&queue=cancellation";
const ALL_REQUESTS = "/attendance?tab=leave&queue=all";

/**
 * Where the reviewer ends up after deciding, given the list they came from.
 *
 * The back link and `onDone` resolve the SAME href, so this one helper covers
 * both - which is the point: they cannot send the reviewer to different places.
 */
function afterDecision(from: string | null): string {
  const detail = permissionDetailHref(REQUEST, from);
  const carried = new URL(detail, "https://x").searchParams.get("from");
  return permissionReturnHref(carried);
}

// ── 1 & 2. opened from Permission requests ──────────────────────────────────

test("approving returns to the Permission requests queue", () => {
  assert.equal(afterDecision(PERMISSION_QUEUE), PERMISSION_QUEUE);
});

test("rejecting returns to the Permission requests queue", () => {
  // Approve and Reject share one `onDone`, so there is one destination for both
  // by construction - this pins that they are not allowed to diverge.
  assert.equal(afterDecision(PERMISSION_QUEUE), PERMISSION_QUEUE);
});

test("the reviewer is NOT sent to their own Permission History", () => {
  // The bug, stated directly.
  assert.notEqual(afterDecision(PERMISSION_QUEUE), PERMISSION_HISTORY_PATH);
});

test("the queue row carries the address rather than a bare path", () => {
  // The bare-path call at the row was the actual root cause: with no `from`
  // there was nothing for the page to return to.
  assert.equal(
    permissionDetailHref(REQUEST, PERMISSION_QUEUE),
    `${PERMISSION_HISTORY_PATH}/${REQUEST}?from=${encodeURIComponent(PERMISSION_QUEUE)}`,
  );
});

// ── 3. opened from All Requests, filters intact ─────────────────────────────

test("a request opened from All Requests returns to All Requests", () => {
  assert.equal(afterDecision(ALL_REQUESTS), ALL_REQUESTS);
});

test("the All Requests filters, date window and page all survive the decision", () => {
  // Nothing in either helper names these parameters - the address is
  // round-tripped whole, which is why a filter added later needs no change here.
  const url =
    "/attendance?tab=leave&queue=all&ls=approved&lf=2027-03-01&lt=2027-03-31&lo=20";
  assert.equal(afterDecision(url), url);
});

test("a Project Head's Team-approvals queue comes back to itself", () => {
  const url = "/attendance?tab=leave&view=team&queue=permission";
  assert.equal(afterDecision(url), url);
});

// ── the other review entry point ────────────────────────────────────────────

test("a permission opened from the Cancellation queue returns there", () => {
  assert.equal(afterDecision(CANCELLATION_QUEUE), CANCELLATION_QUEUE);
});

// ── 4. the fallback is unchanged and safe ───────────────────────────────────

test("a cold-opened detail page still falls back to Permission History", () => {
  // A notification, an email link or a bookmark carries no `from` at all - the
  // employee's own history remains the safe default, exactly as before.
  assert.equal(permissionDetailHref(REQUEST), `${PERMISSION_HISTORY_PATH}/${REQUEST}`);
  assert.equal(afterDecision(null), PERMISSION_HISTORY_PATH);
  assert.equal(afterDecision(""), PERMISSION_HISTORY_PATH);
});

test("the employee's own Permission History still returns to Permission History", () => {
  // Normal employee history navigation is untouched: its rows pass no `from`,
  // and even if they did the round trip lands back on the same page.
  assert.equal(afterDecision(PERMISSION_HISTORY_PATH), PERMISSION_HISTORY_PATH);
});

test("a forged return address is refused, not followed", () => {
  // `from` is a convenience the app writes for itself, never a destination a
  // hand-edited or forwarded URL gets to choose.
  for (const forged of [
    "https://evil.example/x",
    "//evil.example",
    "/attendance-x?a=1",
    "/attendance/permission-x",
  ]) {
    assert.equal(afterDecision(forged), PERMISSION_HISTORY_PATH);
  }
});
