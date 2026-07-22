/**
 * Pure-logic guards for activity access control.
 *
 * The repo's frontend test harness is `node --test` over `src/**​/*.test.ts`
 * (see package.json `test:unit`) — plain TypeScript, no jsdom / React Testing
 * Library. So this file pins the pure helpers the access UI depends on:
 *   - canSearchEmployees: the >= 2-char search threshold shared by the hook's
 *     query `enabled` and the search box (they must never disagree).
 *   - employeeLabel: the name shown in chips / result rows.
 *
 * Component-interaction behaviour (lazy tab fetch, debounce timing, optimistic
 * state) is intentionally NOT covered here — asserting it would require adding a
 * component-test framework this project deliberately does not ship.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canSearchEmployees,
  employeeLabel,
  EMPLOYEE_SEARCH_MIN_CHARS,
} from "./types.ts";

test("search stays disabled below the minimum length", () => {
  assert.equal(EMPLOYEE_SEARCH_MIN_CHARS, 2);
  assert.equal(canSearchEmployees(""), false);
  assert.equal(canSearchEmployees("a"), false);
});

test("search fires at and above the minimum length", () => {
  assert.equal(canSearchEmployees("ab"), true);
  assert.equal(canSearchEmployees("abc"), true);
});

test("leading/trailing whitespace does not count toward the threshold", () => {
  assert.equal(canSearchEmployees("  "), false);
  assert.equal(canSearchEmployees(" a "), false);
  assert.equal(canSearchEmployees(" ab "), true);
});

test("employeeLabel joins first and last name", () => {
  assert.equal(
    employeeLabel({ id: "1", employee_code: "E1", first_name: "Asha", last_name: "Rao" }),
    "Asha Rao",
  );
});

test("employeeLabel trims a missing last name cleanly", () => {
  assert.equal(
    employeeLabel({ id: "1", employee_code: "E1", first_name: "Asha", last_name: "" }),
    "Asha",
  );
});
