/**
 * All leave -> row click -> Leave Detail -> "← Leave" -> All leave.
 *
 * The round trip is `leaveDetailHref` (what the row navigates to) followed by
 * `leaveReturnHref` (what the back link resolves to), and it is a round trip on
 * purpose: the list hands over its OWN current address rather than a rebuilt
 * one, so the queue, the status filter, the date window and the page number all
 * come back without any of them being named here. These tests are the All-leave
 * case of that - the same two functions the Pending and Cancellation queues
 * already go through.
 *
 * There is no DOM test runner in this repo by design; the row's onClick is a
 * manual check. What is testable, and what actually decides whether the reader
 * lands back on All leave, is the pair of pure functions below.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { LEAVE_LIST_HREF, leaveDetailHref, leaveReturnHref } from "./types.ts";

const REQUEST = "3f2a91c4-0000-4000-8000-000000000001";

/** The All-leave tab as the panel's own URL actually looks. */
const ALL_LEAVE = "/attendance?tab=leave&queue=all";

function roundTrip(from: string): string {
  const detail = leaveDetailHref(REQUEST, from);
  const back = new URL(detail, "https://x").searchParams.get("from");
  return leaveReturnHref(back);
}

// ── A. the row opens the SHARED detail route ────────────────────────────────

test("a row opens the existing /attendance/leave/{id} page", () => {
  // Not an All-leave-specific detail page: the same route the Pending queue
  // opens, so the Phase 2 layout and its review rules are reached unchanged.
  assert.ok(leaveDetailHref(REQUEST, ALL_LEAVE).startsWith(`/attendance/leave/${REQUEST}?`));
});

test("the row carries the All-leave address it was clicked from", () => {
  assert.equal(
    leaveDetailHref(REQUEST, ALL_LEAVE),
    `/attendance/leave/${REQUEST}?from=${encodeURIComponent(ALL_LEAVE)}`,
  );
});

// ── B. "← Leave" comes back to All leave ────────────────────────────────────

test("← Leave returns to the All-leave tab, not the default Leave view", () => {
  assert.equal(roundTrip(ALL_LEAVE), ALL_LEAVE);
});

test("the status filter survives the round trip", () => {
  const url = "/attendance?tab=leave&queue=all&ls=approved";
  assert.equal(roundTrip(url), url);
});

test("the date window survives the round trip", () => {
  const url = "/attendance?tab=leave&queue=all&lf=2026-09-01&lt=2026-09-30";
  assert.equal(roundTrip(url), url);
});

test("the date window, the status filter and the page all survive together", () => {
  // Nothing in either function names these parameters - the address is
  // round-tripped whole, which is why a filter added later needs no change here.
  const url = "/attendance?tab=leave&queue=all&ls=approved&lf=2026-09-01&lt=2026-09-30&lo=20";
  assert.equal(roundTrip(url), url);
});

test("a Project Head's Team-approvals All-leave tab comes back to itself", () => {
  const url = "/attendance?tab=leave&view=team&queue=all&ls=rejected";
  assert.equal(roundTrip(url), url);
});

// ── the other queues are unaffected ─────────────────────────────────────────

test("the Pending and Cancellation queues still round-trip to themselves", () => {
  for (const url of [
    "/attendance?tab=leave&queue=pending",
    "/attendance?tab=leave&queue=cancellation",
  ]) {
    assert.equal(roundTrip(url), url);
  }
});

// ── a page reached without a list behind it ─────────────────────────────────

test("a cold-opened detail page still falls back to the plain Leave tab", () => {
  // An email link or a bookmark carries no `from` at all.
  assert.equal(leaveDetailHref(REQUEST), `/attendance/leave/${REQUEST}`);
  assert.equal(leaveReturnHref(null), LEAVE_LIST_HREF);
});

test("a forged return address is still refused", () => {
  // Unchanged from Phase 2 - `from` is a convenience the app writes for itself,
  // never a destination a hand-edited URL gets to choose.
  for (const forged of ["https://evil.example/x", "//evil.example", "/attendance-x?a=1"]) {
    assert.equal(leaveReturnHref(forged), LEAVE_LIST_HREF);
  }
});
