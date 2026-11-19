/**
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildListQuery,
  canSubmitDecision,
  dayPartLabel,
  employeeLabel,
  hasActiveFilters,
} from "./labels.ts";
import type { ReworkFilters } from "./types";

const EMPTY: ReworkFilters = {
  status: "", project_id: "", employee_id: "", report_date: "", sub_activity_id: "", offset: 0,
};

test("empty filters send only paging", () => {
  assert.equal(buildListQuery(EMPTY), "limit=10&offset=0");
  assert.equal(hasActiveFilters(EMPTY), false);
});

test("filters combine and blank ones are dropped", () => {
  const q = new URLSearchParams(
    buildListQuery({ ...EMPTY, status: "pending", project_id: "p1", report_date: "2026-11-17", offset: 20 }),
  );
  assert.equal(q.get("status"), "pending");
  assert.equal(q.get("project_id"), "p1");
  assert.equal(q.get("report_date"), "2026-11-17");
  assert.equal(q.get("employee_id"), null);
  assert.equal(q.get("offset"), "20");
  assert.equal(hasActiveFilters({ ...EMPTY, employee_id: "e1" }), true);
});

test("labels", () => {
  assert.equal(dayPartLabel("second_half"), "Second Half");
  assert.equal(dayPartLabel(null), "-");
  assert.equal(employeeLabel("CDC031", "ABIRAMI S"), "CDC031 - ABIRAMI S");
  assert.equal(employeeLabel("", "ABIRAMI S"), "ABIRAMI S");
});

test("rejection requires remarks, approval does not", () => {
  assert.equal(canSubmitDecision("approve", ""), true);
  assert.equal(canSubmitDecision("reject", "   "), false);
  assert.equal(canSubmitDecision("reject", "Use design"), true);
});
