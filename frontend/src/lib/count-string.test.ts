/**
 * Regression guard for the count-input keystroke filter.
 *
 * Background: a Work Report count would intermittently save 81 after the user
 * had typed 83. Root cause was the native `<Input type="number">` — a focused
 * number input increments/decrements on mouse wheel, and users type a count
 * then scroll down to reach Save. The fix replaced it with a text input whose
 * every keystroke is vetted by isCountString.
 *
 * These tests pin the accept/reject contract. isCountString must stay a pure
 * predicate: it never converts, clamps or trims — schema validation and the
 * API-body converter (work-reports/schemas.ts `toCount`) remain authoritative.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { isCountString } from "./count-string.ts";

test("accepts an ordinary typed count", () => {
  assert.equal(isCountString("8"), true);
  assert.equal(isCountString("83"), true);
  assert.equal(isCountString("0"), true);
});

test("accepts the empty string so the field can be cleared with backspace", () => {
  // Mid-edit emptiness must stay editable rather than snapping back to "0".
  assert.equal(isCountString(""), true);
});

test("accepts a pasted integer", () => {
  assert.equal(isCountString("125"), true);
});

test("accepts leading zeros without rewriting them", () => {
  // Not our job to normalise while typing; toCount does that at the boundary.
  assert.equal(isCountString("083"), true);
});

test("rejects a negative sign", () => {
  assert.equal(isCountString("-"), false);
  assert.equal(isCountString("-1"), false);
});

test("rejects a decimal point", () => {
  assert.equal(isCountString("8.3"), false);
  assert.equal(isCountString("8."), false);
});

test("rejects scientific notation and plus signs", () => {
  // The four characters a native number input silently tolerates.
  assert.equal(isCountString("8e3"), false);
  assert.equal(isCountString("8E3"), false);
  assert.equal(isCountString("+8"), false);
  assert.equal(isCountString("e"), false);
});

test("rejects spaces", () => {
  assert.equal(isCountString(" "), false);
  assert.equal(isCountString(" 8"), false);
  assert.equal(isCountString("8 "), false);
  assert.equal(isCountString("8 3"), false);
});

test("rejects letters and punctuation", () => {
  assert.equal(isCountString("abc"), false);
  assert.equal(isCountString("8a"), false);
  assert.equal(isCountString("8,3"), false);
});

test("rejects non-ASCII digits", () => {
  // \d in a non-unicode regex is ASCII-only; pin that this stays true so an
  // IME or numeric keypad cannot smuggle a non-parseable digit through.
  assert.equal(isCountString("٣"), false);
  assert.equal(isCountString("８３"), false);
});

test("rejects a newline (rules out multiline paste)", () => {
  assert.equal(isCountString("8\n3"), false);
  assert.equal(isCountString("83\n"), false);
});
