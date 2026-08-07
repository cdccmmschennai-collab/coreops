/**
 * Pure-logic tests for the "no further tags were available" exception rules.
 *
 * Harness: `node --test` over src/**​/*.test.ts (see package.json test:unit) —
 * plain TypeScript, no jsdom / React Testing Library. The editor deliberately
 * delegates BOTH the checkbox's visibility and every "clears automatically"
 * rule to canShowNoFurtherWorkException / resolveExceptionCode, so those rules
 * are fully pinned here even though the component itself cannot be mounted.
 * The server re-validates independently (see backend
 * tests/test_benchmark_exception.py).
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { BenchmarkType, RelevantCountField } from "../activity-master/types.ts";
import {
  BENCHMARK_EXCEPTION_NO_FURTHER_AVAILABLE_WORK as NO_FURTHER,
  canShowNoFurtherWorkException,
  parseActual,
  resolveExceptionCode,
} from "./benchmark-exception.ts";

/** A numeric TAGS row, target 100, 40 entered — the approved example. */
function input(over: {
  benchmarkType?: BenchmarkType | null;
  countField?: RelevantCountField | null;
  target?: number | null;
  actual?: string | number | null;
} = {}) {
  return {
    benchmarkType: "NUMERIC_DAILY" as BenchmarkType | null,
    countField: "tags" as RelevantCountField | null,
    target: 100 as number | null,
    actual: "40" as string | number | null,
    ...over,
  };
}

// --- parseActual -------------------------------------------------------------

test("parseActual treats blank and invalid entries as no value", () => {
  assert.equal(parseActual(""), null);
  assert.equal(parseActual("   "), null);
  assert.equal(parseActual("abc"), null);
  assert.equal(parseActual("-3"), null);
  assert.equal(parseActual(null), null);
  assert.equal(parseActual(undefined), null);
  assert.equal(parseActual(Number.NaN), null);
});

test("parseActual keeps zero — 'none were available' is a real entry", () => {
  assert.equal(parseActual("0"), 0);
  assert.equal(parseActual(0), 0);
  assert.equal(parseActual("40"), 40);
  assert.equal(parseActual(" 40 "), 40);
});

// --- visibility --------------------------------------------------------------

test("checkbox is hidden until an actual value is entered", () => {
  assert.equal(canShowNoFurtherWorkException(input({ actual: "" })), false);
  assert.equal(canShowNoFurtherWorkException(input({ actual: null })), false);
  assert.equal(canShowNoFurtherWorkException(input({ actual: "abc" })), false);
});

test("checkbox is visible when the entered actual is below target", () => {
  assert.equal(canShowNoFurtherWorkException(input()), true);
  assert.equal(canShowNoFurtherWorkException(input({ actual: "0" })), true);
  assert.equal(canShowNoFurtherWorkException(input({ actual: "99" })), true);
});

test("checkbox is hidden once the actual reaches or passes the target", () => {
  assert.equal(canShowNoFurtherWorkException(input({ actual: "100" })), false);
  assert.equal(canShowNoFurtherWorkException(input({ actual: "140" })), false);
});

test("checkbox is unavailable for task-based activities", () => {
  for (const t of ["TASK_BASED", "TASK_STATUS_ONLY", "TASK_WITH_QUANTITY"] as BenchmarkType[]) {
    assert.equal(
      canShowNoFurtherWorkException(input({ benchmarkType: t })),
      false,
      t,
    );
  }
  assert.equal(canShowNoFurtherWorkException(input({ benchmarkType: null })), false);
});

test("checkbox is unavailable for non-Tag metrics in Phase 1", () => {
  for (const u of ["docs", "bom", "spares", "pages", "records"] as RelevantCountField[]) {
    assert.equal(canShowNoFurtherWorkException(input({ countField: u })), false, u);
  }
  assert.equal(canShowNoFurtherWorkException(input({ countField: null })), false);
});

test("checkbox needs a valid positive target", () => {
  assert.equal(canShowNoFurtherWorkException(input({ target: null })), false);
  assert.equal(canShowNoFurtherWorkException(input({ target: 0 })), false);
  assert.equal(canShowNoFurtherWorkException(input({ target: -10 })), false);
  assert.equal(canShowNoFurtherWorkException(input({ target: Number.NaN })), false);
});

test("the legacy NUMERIC mode is still eligible", () => {
  assert.equal(
    canShowNoFurtherWorkException(input({ benchmarkType: "NUMERIC" })),
    true,
  );
});

// --- clearing ----------------------------------------------------------------

test("a saved exception is restored while its conditions still hold", () => {
  assert.equal(resolveExceptionCode(input(), NO_FURTHER), NO_FURTHER);
});

test("an unset exception is never invented", () => {
  assert.equal(resolveExceptionCode(input(), ""), null);
  assert.equal(resolveExceptionCode(input(), null), null);
  assert.equal(resolveExceptionCode(input(), undefined), null);
  // An unrecognised stored value is not honoured either.
  assert.equal(resolveExceptionCode(input(), "SOMETHING_ELSE"), null);
});

test("changing the activity clears the exception", () => {
  // A new activity means a new benchmark: task mode, another unit, or another
  // target — each of these drops it.
  assert.equal(
    resolveExceptionCode(input({ benchmarkType: "TASK_STATUS_ONLY" }), NO_FURTHER),
    null,
  );
  assert.equal(resolveExceptionCode(input({ countField: "pages" }), NO_FURTHER), null);
  assert.equal(resolveExceptionCode(input({ target: null }), NO_FURTHER), null);
});

test("changing the benchmark target below the entered actual clears it", () => {
  // 40 entered against a target that dropped to 30: nothing is outstanding, so
  // there is nothing to except.
  assert.equal(resolveExceptionCode(input({ target: 30 }), NO_FURTHER), null);
});

test("raising the actual to the target clears the exception", () => {
  assert.equal(resolveExceptionCode(input({ actual: "100" }), NO_FURTHER), null);
  assert.equal(resolveExceptionCode(input({ actual: "140" }), NO_FURTHER), null);
});

test("emptying or invalidating the actual clears the exception", () => {
  assert.equal(resolveExceptionCode(input({ actual: "" }), NO_FURTHER), null);
  assert.equal(resolveExceptionCode(input({ actual: "   " }), NO_FURTHER), null);
  assert.equal(resolveExceptionCode(input({ actual: "abc" }), NO_FURTHER), null);
  assert.equal(resolveExceptionCode(input({ actual: null }), NO_FURTHER), null);
});
