/**
 * Support Missing Project Codes — the free-text Project Code the employee
 * types when the SELECTED project has no code of its own.
 *
 * Whether the field is actually REQUIRED depends on the live-selected
 * project's own code, which this static zod schema cannot see — that check
 * runs in work-report-form.tsx's validateProjectCodes (same shape as its
 * neighbouring validateBenchmarks/validateLumpsumCounts) and is exercised by
 * hand per the manual verification steps, not here. What IS pinned here is
 * the pure, schema-level plumbing: what reaches the server, and what a
 * reopened no-code-project row pre-fills with.
 *
 * Pairs with backend tests/test_work_report_project_code_fallback.py, which
 * pins the server-side 422 and the storage/never-writes-the-Project-Master
 * behaviour.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { EMPTY_TASK_ROW, EMPTY_WORK_REPORT_FORM, toCreateBody, toFormValues } from "./schemas.ts";
import type { WorkReportFormValues } from "./schemas.ts";
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

// ── what is sent ─────────────────────────────────────────────────────────────

test("the manual code is sent to the server", () => {
  const body = toCreateBody(formWithTask({ manual_project_code: "TAG-EST-2026" }));

  assert.equal(firstTask(body).manual_project_code, "TAG-EST-2026");
});

test("an empty manual code is sent as null, never an empty string", () => {
  const body = toCreateBody(formWithTask({}));

  assert.equal(firstTask(body).manual_project_code, null);
});

test("whitespace-only entry is sent as null", () => {
  const body = toCreateBody(formWithTask({ manual_project_code: "   " }));

  assert.equal(firstTask(body).manual_project_code, null);
});

// ── what comes back ──────────────────────────────────────────────────────────

test("reopening a no-code project's row pre-fills the manual entry from the saved value", () => {
  const values = toFormValues(savedReport({ project_code: "TAG-EST-2026" }));

  assert.equal(values.tasks[0].project_code, "TAG-EST-2026");
  assert.equal(values.tasks[0].manual_project_code, "TAG-EST-2026");
});

test("reopening a coded project's row carries the same value into both fields", () => {
  // Harmless: PeriodActivityEditor only shows/uses manual_project_code when
  // the LIVE project turns out to have no code, which this row's project
  // does — so the leftover value here is simply never read.
  const values = toFormValues(savedReport({ project_code: "4391-GC21107300" }));

  assert.equal(values.tasks[0].project_code, "4391-GC21107300");
  assert.equal(values.tasks[0].manual_project_code, "4391-GC21107300");
});
