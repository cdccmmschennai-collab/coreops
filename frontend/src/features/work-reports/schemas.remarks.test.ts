/**
 * Remarks routing at the API boundary.
 *
 * Full Day keeps the single report-level `remarks`. Split Day uses ONLY the
 * two period-level remarks: each half's text travels on its own period, the
 * header remark is forced null (a stale Day Remark must never ride along),
 * and the two are never merged. toFormValues restores each remark into the
 * correct half on reopen.
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

/** A filled Split-Day form: leave first half, working second half, and a
 *  stale report-level remark that must NOT reach a split payload. */
function splitForm(): WorkReportFormValues {
  return {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-19",
    day_format: "split_day",
    location: "chennai",
    first_half: {
      status: "leave",
      remarks: "Medical appointment",
    },
    second_half: {
      status: "work_at_office",
      remarks: "Completed MTL asset-photo verification",
    },
    remarks: "stale full-day remark",
    tasks: [{ ...EMPTY_TASK_ROW, day_part: "second_half", project_id: "p1" }],
  };
}

type SplitBody = {
  remarks?: string | null;
  periods?: { day_part: string; remarks: string | null }[];
};

function periodsByPart(body: SplitBody) {
  assert.ok(Array.isArray(body.periods), "split body carries periods");
  return Object.fromEntries(body.periods!.map((p) => [p.day_part, p]));
}

test("split create body puts each remark on its own half", () => {
  const parts = periodsByPart(toCreateBody(splitForm()) as SplitBody);
  assert.equal(parts.first_half.remarks, "Medical appointment");
  assert.equal(parts.second_half.remarks, "Completed MTL asset-photo verification");
});

test("split create body never sends a report-level remark", () => {
  const body = toCreateBody(splitForm()) as SplitBody;
  assert.equal(body.remarks, null);
});

test("split update body never sends a report-level remark", () => {
  const body = toUpdateBody(splitForm()) as SplitBody;
  assert.equal(body.remarks, null);
  const parts = periodsByPart(body);
  assert.equal(parts.first_half.remarks, "Medical appointment");
  assert.equal(parts.second_half.remarks, "Completed MTL asset-photo verification");
});

test("period remarks are optional — empty sends null, not ''", () => {
  const form = splitForm();
  form.first_half.remarks = "";
  form.second_half.remarks = "   ";
  const parts = periodsByPart(toCreateBody(form) as SplitBody);
  assert.equal(parts.first_half.remarks, null);
  assert.equal(parts.second_half.remarks, null);
});

test("full-day bodies keep the report-level remark unchanged", () => {
  const form: WorkReportFormValues = {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-19",
    day_status: "work_at_office",
    location: "chennai",
    remarks: "classic day remark",
    tasks: [{ ...EMPTY_TASK_ROW, project_id: "p1" }],
  };
  assert.equal(toCreateBody(form).remarks, "classic day remark");
  assert.equal(toUpdateBody(form).remarks, "classic day remark");
});

/** Minimal WorkReport for toFormValues round-trips. */
function apiReport(overrides: Record<string, unknown>): WorkReport {
  return {
    id: "r1",
    employee_id: "e1",
    report_date: "2026-07-19",
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

test("reopening a split draft restores each remark into the correct half", () => {
  const values = toFormValues(
    apiReport({
      report_mode: "split_day",
      periods: [
        { id: "p2", day_part: "second_half", period_status: "work_at_office",
          location: "chennai", remarks: "PM work", work_fraction: "0.5",
          is_legacy_half_day: false, tasks: [] },
        { id: "p1", day_part: "first_half", period_status: "leave",
          location: null, remarks: "AM leave", work_fraction: "0.5",
          is_legacy_half_day: false, tasks: [] },
      ],
    }),
  );
  assert.equal(values.day_format, "split_day");
  assert.equal(values.first_half.remarks, "AM leave");
  assert.equal(values.second_half.remarks, "PM work");
});

test("reopening a full-day report restores the report-level remark", () => {
  const values = toFormValues(apiReport({ remarks: "classic day remark" }));
  assert.equal(values.day_format, "full_day");
  assert.equal(values.remarks, "classic day remark");
  assert.equal(values.first_half.remarks, "");
  assert.equal(values.second_half.remarks, "");
});
