/**
 * Full Day and Split Day are independent modes, not two views of one array.
 *
 * The form keeps ONE flat `tasks` array with a per-row `day_part` stamp, so
 * isolation rests on two contracts pinned here:
 *   - payloads: a Full-Day body carries ONLY full_day rows, a Split-Day body
 *     carries ONLY rows explicitly stamped first_half / second_half (a stray
 *     row from the other mode is dropped, never re-inferred);
 *   - toFormValues: the persisted report_mode populates only its own mode's
 *     state — the inactive mode starts blank.
 * (The mode-switch confirmation + clearing itself lives in the form component;
 * no DOM test runner exists, so that part is verified manually.)
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import type { WorkReport } from "./types.ts";
import {
  EMPTY_TASK_ROW,
  EMPTY_WORK_REPORT_FORM,
  toCreateBody,
  toFormValues,
  toUpdateBody,
  type WorkReportFormValues,
} from "./schemas.ts";

type BodyTask = { project_id?: string; work_item_id?: string | null };

type AnyBody = {
  report_mode?: string;
  tasks?: BodyTask[];
  periods?: { day_part: string; tasks: BodyTask[] }[];
};

const fullRow = (over: Partial<WorkReportFormValues["tasks"][number]> = {}) => ({
  ...EMPTY_TASK_ROW,
  project_id: "p-full",
  activity_id: "a1",
  sub_activity_id: "s-full",
  ...over,
});

test("Full-Day body sends only full_day rows — stray half rows are dropped", () => {
  const form: WorkReportFormValues = {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-20",
    day_status: "work_at_office",
    location: "chennai",
    tasks: [
      fullRow(),
      fullRow({ day_part: "first_half", project_id: "p-stray1" }),
      fullRow({ day_part: "second_half", project_id: "p-stray2" }),
    ],
  };
  for (const body of [toCreateBody(form), toUpdateBody(form)] as AnyBody[]) {
    assert.equal(body.periods, undefined, "full-day body has no periods");
    assert.equal(body.tasks!.length, 1);
    assert.equal(body.tasks![0].project_id, "p-full");
  }
});

test("Split-Day body sends only explicitly-stamped half rows — full_day rows never become First Half", () => {
  const form: WorkReportFormValues = {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-20",
    day_format: "split_day",
    location: "chennai",
    first_half: { status: "work_at_office", remarks: "" },
    second_half: { status: "work_at_office", remarks: "" },
    tasks: [
      fullRow({ project_id: "p-stray" }), // day_part full_day — must not leak
      fullRow({ day_part: "first_half", project_id: "p-fh" }),
      fullRow({ day_part: "second_half", project_id: "p-sh" }),
    ],
  };
  for (const body of [toCreateBody(form), toUpdateBody(form)] as AnyBody[]) {
    assert.equal(body.report_mode, "split_day");
    assert.equal(body.tasks, undefined, "split body has no flat task list");
    const parts = Object.fromEntries(body.periods!.map((p) => [p.day_part, p]));
    assert.deepEqual(parts.first_half.tasks.map((t) => t.project_id), ["p-fh"]);
    assert.deepEqual(parts.second_half.tasks.map((t) => t.project_id), ["p-sh"]);
  }
});

test("continuation rows never enter a Split-Day payload", () => {
  const form: WorkReportFormValues = {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-20",
    day_format: "split_day",
    location: "chennai",
    first_half: { status: "leave", remarks: "" },
    second_half: { status: "work_at_office", remarks: "" },
    // A leftover Full-Day continuation row (work_item_id set).
    tasks: [fullRow({ work_item_id: "wi-1" })],
  };
  const body = toCreateBody(form) as AnyBody;
  const allPeriodTasks = body.periods!.flatMap((p) => p.tasks);
  assert.equal(allPeriodTasks.length, 0);
  assert.ok(
    !JSON.stringify(body).includes("wi-1"),
    "work_item_id must not appear anywhere in the split body",
  );
});

/** Minimal WorkReport for toFormValues round-trips. */
function apiReport(overrides: Record<string, unknown>): WorkReport {
  return {
    id: "r1",
    employee_id: "e1",
    report_date: "2026-07-20",
    status: "draft",
    report_mode: "full_day",
    periods: [],
    remarks: null,
    query_text: null,
    total_minutes: 0,
    tasks: [],
    ...overrides,
  } as unknown as WorkReport;
}

const apiTask = (over: Record<string, unknown>) => ({
  id: "t1",
  project_id: "p1",
  description: "",
  minutes_spent: null,
  task_minutes_spent: null,
  activity_type: null,
  sub_activity_id: "s1",
  tags_count: 0, docs_count: 0, bom_count: 0,
  spares_count: 0, pages_count: 0, records_count: 0,
  is_completed: false,
  ...over,
});

test("loading a Full-Day report populates only Full-Day state", () => {
  const values = toFormValues(
    apiReport({
      day_status: "work_at_office",
      location: "chennai",
      remarks: "day note",
      tasks: [apiTask({ day_part: "full_day" })],
    }),
  );
  assert.equal(values.day_format, "full_day");
  assert.equal(values.day_status, "work_at_office");
  assert.ok(values.tasks.every((t) => t.day_part === "full_day"));
  // Halves stay blank — nothing is mapped into First/Second Half.
  assert.equal(values.first_half.status, undefined);
  assert.equal(values.second_half.status, undefined);
  assert.equal(values.first_half.remarks, "");
  assert.equal(values.second_half.remarks, "");
});

test("loading a Split-Day report populates only period state", () => {
  const values = toFormValues(
    apiReport({
      report_mode: "split_day",
      day_status: "half_day", // server-derived header — not Full-Day input
      location: "chennai",
      periods: [
        { id: "p1", day_part: "first_half", period_status: "leave",
          location: null, remarks: "AM leave", work_fraction: "0.5",
          is_legacy_half_day: false, tasks: [] },
        { id: "p2", day_part: "second_half", period_status: "work_at_office",
          location: "chennai", remarks: "PM work", work_fraction: "0.5",
          is_legacy_half_day: false, tasks: [] },
      ],
      tasks: [apiTask({ day_part: "second_half" })],
    }),
  );
  assert.equal(values.day_format, "split_day");
  assert.equal(values.first_half.status, "leave");
  assert.equal(values.second_half.status, "work_at_office");
  assert.ok(values.tasks.every((t) => t.day_part !== "full_day"));
  // Full-Day mode state stays blank: the derived header day_status is not
  // Full-Day input, and Day Remarks never mirrors period remarks.
  assert.equal(values.day_status, undefined);
  assert.equal(values.remarks, "");
  // The one report-level Location is shared state and IS restored.
  assert.equal(values.location, "chennai");
});
