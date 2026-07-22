/**
 * Day Remarks line rendering for the PM Weekly Activity Report preview. The
 * backend joins a split-day report's half-remarks with a newline; the Remarks
 * cell renders each segment on its own visible line via remarkLines().
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { remarkLines } from "./remarks.ts";

test("split-day combined remarks render as two visible lines", () => {
  const combined =
    "First Half: worked on this docs in first half\n" +
    "Second Half: worked on two activities";
  assert.deepEqual(remarkLines(combined), [
    "First Half: worked on this docs in first half",
    "Second Half: worked on two activities",
  ]);
});

test("first-half-only combined remark renders one line", () => {
  assert.deepEqual(remarkLines("First Half: only the morning"), [
    "First Half: only the morning",
  ]);
});

test("full-day remark renders as a single line, unchanged", () => {
  assert.deepEqual(remarkLines("a normal full day note"), [
    "a normal full day note",
  ]);
});

test("blank / null remarks render no lines (empty cell)", () => {
  assert.deepEqual(remarkLines(""), []);
  assert.deepEqual(remarkLines(null), []);
  assert.deepEqual(remarkLines(undefined), []);
});
