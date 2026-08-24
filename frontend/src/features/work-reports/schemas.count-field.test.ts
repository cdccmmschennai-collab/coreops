/**
 * The LS Count row at the API boundary: the picked unit reaches the server,
 * comes back on edit, and never disturbs the "Other counts" values beside it.
 *
 * Pairs with ls-count.test.ts (which pins WHICH unit owns the Count input) and
 * with backend tests/test_lumpsum_count_field.py (which pins storage, the
 * validation of the field name, and the export).
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  EMPTY_TASK_ROW,
  EMPTY_WORK_REPORT_FORM,
  toCreateBody,
  toFormValues,
  workReportFormSchema,
  type WorkReportFormValues,
} from "./schemas.ts";
import type { WorkReport } from "./types.ts";

function firstTask(body: { tasks?: unknown }) {
  const tasks = body.tasks;
  assert.ok(Array.isArray(tasks) && tasks.length > 0, "body carries task rows");
  return tasks[0] as Record<string, unknown>;
}

function formWithTask(
  overrides: Partial<WorkReportFormValues["tasks"][number]>,
): WorkReportFormValues {
  return {
    ...EMPTY_WORK_REPORT_FORM,
    tasks: [{ ...EMPTY_TASK_ROW, project_id: "p1", ...overrides }],
  };
}

/** A form complete enough to pass every OTHER rule, so a failure below can only
 *  be the Count/Field pairing. */
function validatableForm(
  overrides: Partial<WorkReportFormValues["tasks"][number]>,
): WorkReportFormValues {
  return {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-08-24",
    day_status: "work_at_office",
    location: "chennai",
    tasks: [
      {
        ...EMPTY_TASK_ROW,
        project_id: "p1",
        activity_id: "a1",
        sub_activity_id: "s1",
        ...overrides,
      },
    ],
  };
}

/** The issues zod raised against tasks[0].count_field, if any. */
function countFieldIssues(values: WorkReportFormValues) {
  const parsed = workReportFormSchema.safeParse(values);
  if (parsed.success) return [];
  return parsed.error.issues.filter(
    (i) => i.path.join(".") === "tasks.0.count_field",
  );
}

/** A saved report carrying one task row, shaped as the API returns it. */
function savedReport(task: Record<string, unknown>): WorkReport {
  return {
    report_date: "2026-08-24",
    report_mode: "full_day",
    day_status: "work_at_office",
    location: "chennai",
    tasks: [
      {
        project_id: "p1",
        description: "",
        tags_count: 0,
        docs_count: 0,
        bom_count: 0,
        spares_count: 0,
        pages_count: 0,
        records_count: 0,
        ...task,
      },
    ],
  } as unknown as WorkReport;
}

// ── the conditional requirement, at the form ─────────────────────────────────

test("no count and no field passes validation — the activity saves", () => {
  assert.deepEqual(countFieldIssues(validatableForm({})), []);
  assert.equal(workReportFormSchema.safeParse(validatableForm({})).success, true);
});

test("a count typed with no field is blocked, with a usable message", () => {
  const issues = countFieldIssues(validatableForm({ count_value: "25" }));

  assert.equal(issues.length, 1);
  assert.equal(issues[0].message, "Please select a field for the entered count.");
});

test("naming the field clears the block", () => {
  // Naming a field moves the number into that field, so the staging slot is
  // empty again — which is exactly the shape the editor produces.
  const values = validatableForm({ count_field: "tags", tags_count: "25" });

  assert.deepEqual(countFieldIssues(values), []);
  assert.equal(workReportFormSchema.safeParse(values).success, true);
});

test("a zero in the Count is not a count waiting for a field", () => {
  assert.deepEqual(countFieldIssues(validatableForm({ count_value: "0" })), []);
});

test("a field with no count is allowed — the count is never mandatory", () => {
  assert.deepEqual(countFieldIssues(validatableForm({ count_field: "tags" })), []);
});

test("Other counts alone never demand a field", () => {
  // They are attributed by construction: each is typed into its own named input.
  const values = validatableForm({ docs_count: "10", bom_count: "5" });

  assert.deepEqual(countFieldIssues(values), []);
  assert.equal(workReportFormSchema.safeParse(values).success, true);
});

// ── what is sent ─────────────────────────────────────────────────────────────

test("Count 25 under Tags is sent as tags_count 25 + count_field tags", () => {
  const body = toCreateBody(
    formWithTask({ tags_count: "25", count_field: "tags" }),
  );

  assert.equal(firstTask(body).tags_count, 25);
  assert.equal(firstTask(body).count_field, "tags");
});

test("Count 50 under Docs is sent as docs_count 50 + count_field docs", () => {
  const body = toCreateBody(
    formWithTask({ docs_count: "50", count_field: "docs" }),
  );

  assert.equal(firstTask(body).docs_count, 50);
  assert.equal(firstTask(body).count_field, "docs");
});

test("nothing picked is sent as null, never an empty string", () => {
  const body = toCreateBody(formWithTask({}));

  assert.equal(firstTask(body).count_field, null);
  assert.equal(firstTask(body).count_value, null);
});

test("a count that named its field rides in that field, not in count_value", () => {
  const body = toCreateBody(
    formWithTask({ tags_count: "25", count_field: "tags" }),
  );

  assert.equal(firstTask(body).tags_count, 25);
  assert.equal(firstTask(body).count_value, null);
});

test("an unattributed count is still sent, so the server can refuse it", () => {
  // The form blocks this save first; the value goes on the wire only if some
  // other client skips that check, and the server rejects it there.
  const body = toCreateBody(formWithTask({ count_value: "25" }));

  assert.equal(firstTask(body).count_value, 25);
  assert.equal(firstTask(body).count_field, null);
  // It is NOT filed under a guessed column on the way out.
  assert.equal(firstTask(body).tags_count, 0);
});

test("a zero staged count is sent as null", () => {
  const body = toCreateBody(formWithTask({ count_value: "0" }));

  assert.equal(firstTask(body).count_value, null);
});

test("Other counts ride along untouched beside the LS Count", () => {
  const body = toCreateBody(
    formWithTask({
      tags_count:   "25",   // the LS Count
      count_field:  "tags",
      docs_count:   "10",   // entered under "Other counts"
      bom_count:    "5",
      spares_count: "3",
    }),
  );

  assert.deepEqual(
    {
      tags:   firstTask(body).tags_count,
      docs:   firstTask(body).docs_count,
      bom:    firstTask(body).bom_count,
      spares: firstTask(body).spares_count,
      field:  firstTask(body).count_field,
    },
    { tags: 25, docs: 10, bom: 5, spares: 3, field: "tags" },
  );
});

// ── what comes back ──────────────────────────────────────────────────────────

test("reopening restores the Count value and the picked field", () => {
  const values = toFormValues(
    savedReport({
      tags_count: 25,
      relevant_count_field_snapshot: "tags",
    }),
  );

  assert.equal(values.tasks[0].count_field, "tags");
  assert.equal(values.tasks[0].tags_count, "25");
});

test("reopening keeps the Other counts that were saved with it", () => {
  const values = toFormValues(
    savedReport({
      tags_count: 25,
      docs_count: 10,
      bom_count: 5,
      spares_count: 3,
      relevant_count_field_snapshot: "tags",
    }),
  );

  assert.deepEqual(
    {
      field:  values.tasks[0].count_field,
      tags:   values.tasks[0].tags_count,
      docs:   values.tasks[0].docs_count,
      bom:    values.tasks[0].bom_count,
      spares: values.tasks[0].spares_count,
    },
    { field: "tags", tags: "25", docs: "10", bom: "5", spares: "3" },
  );
});

test("a row saved without a pick comes back unpicked, and still valid", () => {
  const values = toFormValues(savedReport({ relevant_count_field_snapshot: null }));

  assert.equal(values.tasks[0].count_field, "");
  assert.equal(values.tasks[0].count_value, "");
  // The countless activity that was valid when it was saved is still valid on
  // reopen — reopening must never turn a saved row into an unsavable one.
  assert.deepEqual(
    countFieldIssues(
      validatableForm({
        count_field: values.tasks[0].count_field,
        count_value: values.tasks[0].count_value,
      }),
    ),
    [],
  );
});

test("a restored row leaves the staging slot empty", () => {
  // A saved count lives in its own unit's field, so nothing is ever waiting for
  // a field on a reopened row — it cannot come back blocked.
  const values = toFormValues(
    savedReport({ tags_count: 25, relevant_count_field_snapshot: "tags" }),
  );

  assert.equal(values.tasks[0].count_value, "");
  assert.equal(values.tasks[0].tags_count, "25");
});

test("the picked field survives a save/reopen/save round trip", () => {
  const values = toFormValues(
    savedReport({ docs_count: 50, relevant_count_field_snapshot: "docs" }),
  );
  const body = toCreateBody({ ...EMPTY_WORK_REPORT_FORM, ...values });

  assert.equal(firstTask(body).count_field, "docs");
  assert.equal(firstTask(body).docs_count, 50);
});
