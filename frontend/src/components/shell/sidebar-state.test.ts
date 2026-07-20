/**
 * Desktop sidebar preference rules (see sidebar-state.ts).
 *
 * The provider itself is a thin React wrapper over these helpers; there is no
 * DOM test runner in this repo by design, so the decision logic lives here
 * where it can be tested directly.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  NARROW_DESKTOP_MAX,
  NARROW_DESKTOP_MIN,
  NARROW_DESKTOP_QUERY,
  SIDEBAR_STORAGE_PREFIX,
  defaultCollapsedForWidth,
  parseStoredCollapsed,
  pickUserIdentifier,
  resolveInitialCollapsed,
  serializeCollapsed,
  sidebarStorageKey,
} from "./sidebar-state.ts";

// ── identifier selection ───────────────────────────────────────────────────

test("prefers user.id over the employee fallbacks", () => {
  const id = pickUserIdentifier({
    userId: "u-1",
    employeeId: "e-1",
    employeeCode: "EMP225",
  });
  assert.equal(id, "u-1");
});

test("falls back to employee id when there is no user id", () => {
  assert.equal(
    pickUserIdentifier({ employeeId: "e-1", employeeCode: "EMP225" }),
    "e-1",
  );
});

test("falls back to employee code when that is all there is", () => {
  assert.equal(pickUserIdentifier({ employeeCode: "EMP225" }), "EMP225");
});

test("returns null when no identifier is available", () => {
  assert.equal(pickUserIdentifier({}), null);
  assert.equal(
    pickUserIdentifier({ userId: null, employeeId: null, employeeCode: null }),
    null,
  );
});

test("blank and whitespace-only identifiers do not count", () => {
  assert.equal(pickUserIdentifier({ userId: "", employeeId: "   " }), null);
  // A blank higher-priority source must not shadow a usable lower one.
  assert.equal(pickUserIdentifier({ userId: "  ", employeeId: "e-9" }), "e-9");
});

// ── storage key ────────────────────────────────────────────────────────────

test("builds a user-namespaced key", () => {
  assert.equal(
    sidebarStorageKey("u-1"),
    `${SIDEBAR_STORAGE_PREFIX}:u-1`,
  );
});

test("two users get different keys", () => {
  assert.notEqual(sidebarStorageKey("u-1"), sidebarStorageKey("u-2"));
});

test("no identifier yields no key, never a shared anonymous one", () => {
  for (const value of [null, undefined, "", "   "]) {
    assert.equal(sidebarStorageKey(value), null);
  }
});

// ── stored value parsing ───────────────────────────────────────────────────

test('stored "true" reads as collapsed', () => {
  assert.equal(parseStoredCollapsed("true"), true);
});

test('stored "false" reads as expanded', () => {
  assert.equal(parseStoredCollapsed("false"), false);
});

test("malformed stored values read as no preference", () => {
  for (const raw of [null, undefined, "", "TRUE", "1", "0", "yes", "{}", "null"]) {
    assert.equal(parseStoredCollapsed(raw), null, String(raw));
  }
});

test("serialize round-trips through parse", () => {
  for (const value of [true, false]) {
    assert.equal(parseStoredCollapsed(serializeCollapsed(value)), value);
  }
});

// ── viewport default ───────────────────────────────────────────────────────

test("861 through 1100 defaults to collapsed", () => {
  for (const width of [NARROW_DESKTOP_MIN, 900, 1000, NARROW_DESKTOP_MAX]) {
    assert.equal(defaultCollapsedForWidth(width), true, String(width));
  }
});

test("above 1100 defaults to expanded", () => {
  for (const width of [NARROW_DESKTOP_MAX + 1, 1280, 1920]) {
    assert.equal(defaultCollapsedForWidth(width), false, String(width));
  }
});

test("below 861 defaults to expanded (mobile drawer owns that range)", () => {
  for (const width of [320, 768, NARROW_DESKTOP_MIN - 1]) {
    assert.equal(defaultCollapsedForWidth(width), false, String(width));
  }
});

test("the media query matches the documented boundaries", () => {
  // Pins the query string against the constants the tests above assert, so the
  // runtime matchMedia check and defaultCollapsedForWidth cannot drift.
  assert.equal(
    NARROW_DESKTOP_QUERY,
    "(min-width: 861px) and (max-width: 1100px)",
  );
});

// ── initial value ──────────────────────────────────────────────────────────

test("a saved preference overrides the viewport default", () => {
  // Narrow desktop would default to collapsed; the saved "false" wins.
  assert.equal(resolveInitialCollapsed("false", true), false);
  // Wide desktop would default to expanded; the saved "true" wins.
  assert.equal(resolveInitialCollapsed("true", false), true);
});

test("the viewport default applies when nothing is saved", () => {
  assert.equal(resolveInitialCollapsed(null, true), true);
  assert.equal(resolveInitialCollapsed(null, false), false);
});

test("a malformed stored value falls back to the viewport default", () => {
  assert.equal(resolveInitialCollapsed("garbage", true), true);
  assert.equal(resolveInitialCollapsed("garbage", false), false);
});
