/**
 * Pure-logic tests for the whole-unit benchmark target rule.
 *
 * Mirrors backend tests/test_benchmark_scaled_target.py — a target counts real
 * things, so half of an odd benchmark rounds UP rather than showing a fraction
 * of a tag. The two implementations must agree exactly, or the number an
 * employee is shown differs from the one they are measured against.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { scaledTarget } from "./benchmark-target.ts";

test("a full day is the base target unchanged", () => {
  assert.equal(scaledTarget(66, 1), 66);
  assert.equal(scaledTarget(35, 1), 35);
  assert.equal(scaledTarget(0, 1), 0);
});

test("an evenly divisible half-day target keeps its exact value", () => {
  assert.equal(scaledTarget(66, 0.5), 33);
  assert.equal(scaledTarget(100, 0.5), 50);
});

test("an odd half-day target rounds UP to a whole unit", () => {
  // The reported case: 35 tags over a half day is 18, never 17.5 and never 17.
  assert.equal(scaledTarget(35, 0.5), 18);
  assert.equal(scaledTarget(33, 0.5), 17);
  assert.equal(scaledTarget(1, 0.5), 1);
  assert.equal(scaledTarget(3, 0.5), 2);
});

test("rounding is ceiling, not nearest", () => {
  // 17.1 and 17.5 both land on 18 — the benchmark is never discounted.
  assert.equal(scaledTarget(34.2, 0.5), 18);
  assert.equal(scaledTarget(35, 0.5), 18);
  assert.equal(scaledTarget(35.8, 0.5), 18);
});

test("no configured benchmark yields null, distinct from a target of 0", () => {
  assert.equal(scaledTarget(null, 0.5), null);
  assert.equal(scaledTarget(undefined, 0.5), null);
  assert.equal(scaledTarget(Number.NaN, 0.5), null);
  assert.equal(scaledTarget("", 0.5), null);
  assert.equal(scaledTarget("abc", 0.5), null);
  assert.equal(scaledTarget(0, 0.5), 0);
});

test("a Decimal serialised as a JSON string still yields a target", () => {
  // Regression: the API sends benchmark_value as "66.00", not 66. Validating
  // with Number.isFinite BEFORE coercing turned every real target into null and
  // the form rendered "Target: — TAGS / 1d".
  assert.equal(scaledTarget("66.00", 1), 66);
  assert.equal(scaledTarget("66.00", 0.5), 33);
  assert.equal(scaledTarget("35.00", 0.5), 18);
  assert.equal(scaledTarget("35", 0.5), 18);
  assert.equal(scaledTarget("0.00", 1), 0);
});
