/**
 * Regression guard for count conversion at the API boundary.
 *
 * The count inputs keep their React Hook Form value as a *string* (see
 * components/ui/count-input.tsx). This file pins the other half of that
 * contract: toUpdateBody / toCreateBody are the ONLY place a count becomes a
 * number, and the number they send is exactly what the user typed.
 *
 * The original bug shipped 81 to the server after the user had typed 83, so
 * the headline assertion is deliberately literal: 83 in, 83 out.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  EMPTY_TASK_ROW,
  EMPTY_WORK_REPORT_FORM,
  toCreateBody,
  toUpdateBody,
  type WorkReportFormValues,
} from "./schemas.ts";

/**
 * The generated API types mark `tasks` optional, so narrow once here rather
 * than sprinkling non-null assertions through every assertion below. A body
 * that reached the server without its task rows is itself a test failure.
 */
function firstTask(body: { tasks?: unknown }) {
  const tasks = body.tasks;
  assert.ok(Array.isArray(tasks) && tasks.length > 0, "body carries task rows");
  return tasks[0] as Record<string, number>;
}

/** A one-task form with the given count overrides applied to that task. */
function formWithTask(
  overrides: Partial<WorkReportFormValues["tasks"][number]>,
): WorkReportFormValues {
  return {
    ...EMPTY_WORK_REPORT_FORM,
    tasks: [{ ...EMPTY_TASK_ROW, project_id: "p1", ...overrides }],
  };
}

test("a typed 83 reaches the PATCH body as exactly 83", () => {
  const body = toUpdateBody(formWithTask({ tags_count: "83" }));

  assert.equal(firstTask(body).tags_count, 83);
  // Not 81, not 82, not 84 — no nearby number survives a wheel tick anywhere.
  assert.notEqual(firstTask(body).tags_count, 81);
});

test("every task count field converts independently", () => {
  const body = toUpdateBody(
    formWithTask({
      tags_count:    "83",
      docs_count:    "12",
      bom_count:     "7",
      spares_count:  "0",
      pages_count:   "125",
      records_count: "9",
    }),
  );

  assert.deepEqual(
    {
      tags:    firstTask(body).tags_count,
      docs:    firstTask(body).docs_count,
      bom:     firstTask(body).bom_count,
      spares:  firstTask(body).spares_count,
      pages:   firstTask(body).pages_count,
      records: firstTask(body).records_count,
    },
    { tags: 83, docs: 12, bom: 7, spares: 0, pages: 125, records: 9 },
  );
});

test("an empty count becomes 0 rather than NaN or null", () => {
  // The input lets the field go empty mid-edit; the boundary resolves it.
  const body = toUpdateBody(formWithTask({ tags_count: "", docs_count: "" }));

  assert.equal(firstTask(body).tags_count, 0);
  assert.equal(firstTask(body).docs_count, 0);
});

test("a pasted 125 survives conversion", () => {
  const body = toUpdateBody(formWithTask({ pages_count: "125" }));

  assert.equal(firstTask(body).pages_count, 125);
});

test("leading zeros normalise at the boundary, not while typing", () => {
  const body = toUpdateBody(formWithTask({ tags_count: "083" }));

  assert.equal(firstTask(body).tags_count, 83);
});

test("report-level counts convert the same way", () => {
  const body = toUpdateBody({
    ...EMPTY_WORK_REPORT_FORM,
    task_list_count:        "83",
    task_list_op_count:     "12",
    maintenance_item_count: "5",
    maintenance_plan_count: "0",
    tasks: [{ ...EMPTY_TASK_ROW, project_id: "p1" }],
  });

  assert.equal(body.task_list_count, 83);
  assert.equal(body.task_list_op_count, 12);
  assert.equal(body.maintenance_item_count, 5);
  // A zero report-level count is sent as null (|| null), not 0 — pinning the
  // existing behaviour so the count fix is not blamed for it later.
  assert.equal(body.maintenance_plan_count, null);
});

test("create and update agree on count conversion", () => {
  const form = formWithTask({ tags_count: "83", pages_count: "125" });

  const created = toCreateBody(form);
  const updated = toUpdateBody(form);

  assert.equal(firstTask(created).tags_count, firstTask(updated).tags_count);
  assert.equal(firstTask(created).pages_count, firstTask(updated).pages_count);
});

test("counts are never negative even if a value slips past the input", () => {
  // Defence in depth: the input rejects "-", but the boundary clamps anyway.
  const body = toUpdateBody(formWithTask({ tags_count: "-5" as string }));

  assert.equal(firstTask(body).tags_count, 0);
});

test("a fractional value truncates rather than rounding up", () => {
  const body = toUpdateBody(formWithTask({ tags_count: "8.9" as string }));

  assert.equal(firstTask(body).tags_count, 8);
});
