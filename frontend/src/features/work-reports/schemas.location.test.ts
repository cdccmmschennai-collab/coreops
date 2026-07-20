/**
 * One Location per report, both modes.
 *
 * The employee picks Location once, beside Date. Full Day keeps its existing
 * header `location`; Split Day no longer has per-half location controls — the
 * split payload stamps the single report-level Location onto every WORKING
 * period (non-working halves stay null), so the two periods can never carry
 * different locations. Validation anchors on the one header field.
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
  workReportFormSchema,
  type WorkReportFormValues,
} from "./schemas.ts";

type SplitBody = {
  location?: string | null;
  periods?: {
    day_part: string;
    period_status: string | null;
    location: string | null;
  }[];
};

/** Split form: leave first half, working second half, one header Location. */
function splitForm(
  overrides: Partial<WorkReportFormValues> = {},
): WorkReportFormValues {
  return {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-20",
    day_format: "split_day",
    location: "chennai",
    first_half: { status: "leave", remarks: "" },
    second_half: { status: "work_at_office", remarks: "" },
    tasks: [
      {
        ...EMPTY_TASK_ROW,
        day_part: "second_half",
        project_id: "p1",
        activity_id: "a1",
        sub_activity_id: "s1",
      },
    ],
    ...overrides,
  };
}

function periodsByPart(body: SplitBody) {
  assert.ok(Array.isArray(body.periods), "split body carries periods");
  return Object.fromEntries(body.periods!.map((p) => [p.day_part, p]));
}

test("split body stamps the single report Location onto the working half", () => {
  const parts = periodsByPart(toCreateBody(splitForm()) as SplitBody);
  assert.equal(parts.second_half.location, "chennai");
  // Leave half: no location, as before.
  assert.equal(parts.first_half.location, null);
});

test("two working halves always send the SAME location", () => {
  const form = splitForm({
    first_half: { status: "work_at_office", remarks: "" },
    tasks: [
      { ...EMPTY_TASK_ROW, day_part: "first_half", project_id: "p1",
        activity_id: "a1", sub_activity_id: "s1" },
      { ...EMPTY_TASK_ROW, day_part: "second_half", project_id: "p1",
        activity_id: "a1", sub_activity_id: "s1" },
    ],
  });
  for (const body of [toCreateBody(form), toUpdateBody(form)] as SplitBody[]) {
    const parts = periodsByPart(body);
    assert.equal(parts.first_half.location, "chennai");
    assert.equal(parts.second_half.location, "chennai");
  }
});

test("periods stay in First Half, Second Half order", () => {
  const body = toCreateBody(splitForm()) as SplitBody;
  assert.deepEqual(
    body.periods!.map((p) => p.day_part),
    ["first_half", "second_half"],
  );
});

test("half statuses remain independent of each other and of location", () => {
  const parts = periodsByPart(toCreateBody(splitForm()) as SplitBody);
  assert.equal(parts.first_half.period_status, "leave");
  assert.equal(parts.second_half.period_status, "work_at_office");
});

test("a working half requires the report-level Location (not a per-half one)", () => {
  const res = workReportFormSchema.safeParse(splitForm({ location: undefined }));
  assert.equal(res.success, false);
  const paths = res.error!.issues.map((i) => i.path.join("."));
  assert.ok(paths.includes("location"), `expected header location issue, got: ${paths}`);
  assert.ok(
    !paths.some((p) => p.endsWith("_half.location")),
    `no per-half location issues expected, got: ${paths}`,
  );
});

test("two working halves still surface ONE location issue", () => {
  const res = workReportFormSchema.safeParse(
    splitForm({
      location: undefined,
      first_half: { status: "work_at_office", remarks: "" },
      tasks: [
        { ...EMPTY_TASK_ROW, day_part: "first_half", project_id: "p1",
          activity_id: "a1", sub_activity_id: "s1" },
        { ...EMPTY_TASK_ROW, day_part: "second_half", project_id: "p1",
          activity_id: "a1", sub_activity_id: "s1" },
      ],
    }),
  );
  assert.equal(res.success, false);
  const locationIssues = res.error!.issues.filter(
    (i) => i.path.join(".") === "location",
  );
  assert.equal(locationIssues.length, 1);
});

test("a valid split form with one header Location parses", () => {
  const res = workReportFormSchema.safeParse(splitForm());
  assert.equal(res.success, true, JSON.stringify(res.success ? [] : res.error.issues));
});

test("both halves non-working: no location complaint (day_format error instead)", () => {
  const res = workReportFormSchema.safeParse(
    splitForm({
      location: undefined,
      first_half: { status: "leave", remarks: "" },
      second_half: { status: "comp_off", remarks: "" },
      tasks: [],
    }),
  );
  assert.equal(res.success, false);
  const paths = res.error!.issues.map((i) => i.path.join("."));
  assert.ok(!paths.includes("location"), `unexpected location issue: ${paths}`);
  assert.ok(paths.includes("day_format"));
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

test("reopening a split draft restores the single Location", () => {
  const values = toFormValues(
    apiReport({
      report_mode: "split_day",
      // Server-derived header location (the working half's).
      location: "chennai",
      day_status: "half_day",
      periods: [
        { id: "p1", day_part: "first_half", period_status: "leave",
          location: null, remarks: "Medical appointment", work_fraction: "0.5",
          is_legacy_half_day: false, tasks: [] },
        { id: "p2", day_part: "second_half", period_status: "work_at_office",
          location: "chennai", remarks: "Completed MTL verification",
          work_fraction: "0.5", is_legacy_half_day: false, tasks: [] },
      ],
    }),
  );
  assert.equal(values.day_format, "split_day");
  assert.equal(values.location, "chennai");
  assert.equal(values.first_half.status, "leave");
  assert.equal(values.second_half.status, "work_at_office");
});

test("full-day location behavior is unchanged", () => {
  const form: WorkReportFormValues = {
    ...EMPTY_WORK_REPORT_FORM,
    report_date: "2026-07-20",
    day_status: "work_at_office",
    location: "qatar",
    tasks: [{ ...EMPTY_TASK_ROW, project_id: "p1", activity_id: "a1",
              sub_activity_id: "s1" }],
  };
  assert.equal(toCreateBody(form).location, "qatar");
  assert.equal(toUpdateBody(form).location, "qatar");
  const values = toFormValues(apiReport({ location: "qatar" }));
  assert.equal(values.location, "qatar");
});
