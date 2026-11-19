/**
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  PM_APPROVAL_REQUIRED_LABEL,
  buildCorrectionBody,
  correctionBenchmark,
  reportReworkState,
  reworkRowBadge,
} from "./rework-approval.ts";

test("report rework state: rejected > pending > approved > none", () => {
  assert.equal(reportReworkState([]), null);
  assert.equal(reportReworkState([{ rework_approval_status: null }]), null);
  assert.equal(reportReworkState([{ rework_approval_status: "cancelled" }]), null);
  assert.equal(reportReworkState([{ rework_approval_status: "approved" }]), "approved");
  assert.equal(
    reportReworkState([{ rework_approval_status: "approved" }, { rework_approval_status: "pending" }]),
    "pending",
  );
  assert.equal(
    reportReworkState([{ rework_approval_status: "pending" }, { rework_approval_status: "rejected" }]),
    "rejected",
  );
});

const ROW = { project_id: "p1", project_code: "P1", tags_count: 5, docs_count: 2 };

const base = { benchmark_value: null, benchmark_period_days: null, relevant_count_field: null };

test("quantity sub shows the target, scaled to the half and rounded up", () => {
  const sub = { ...base, benchmark_type: "NUMERIC_DAILY", benchmark_value: "35.00", relevant_count_field: "tags" };
  assert.deepEqual(correctionBenchmark(sub, "full_day"), {
    target: 35, unit: "tags", showCompletion: false, periodDays: null,
  });
  assert.equal(correctionBenchmark(sub, "second_half").target, 18);
});

test("lumpsum sub shows only the completion tick", () => {
  const sub = { ...base, benchmark_type: "TASK_STATUS_ONLY", benchmark_period_days: 3 };
  assert.deepEqual(correctionBenchmark(sub, "full_day"), {
    target: null, unit: null, showCompletion: true, periodDays: 3,
  });
  assert.equal(correctionBenchmark({ ...sub, benchmark_type: "TASK_BASED" }, null).showCompletion, true);
});

test("task with quantity shows both", () => {
  const sub = {
    ...base, benchmark_type: "TASK_WITH_QUANTITY", benchmark_value: 500,
    relevant_count_field: "pages", benchmark_period_days: 1,
  };
  const b = correctionBenchmark(sub, "full_day");
  assert.equal(b.target, 500);
  assert.equal(b.unit, "pages");
  assert.equal(b.showCompletion, true);
});

test("no benchmark shows nothing", () => {
  assert.deepEqual(correctionBenchmark({ ...base, benchmark_type: null }, "full_day"), {
    target: null, unit: null, showCompletion: false, periodDays: null,
  });
  assert.equal(correctionBenchmark(undefined, "full_day").target, null);
});

test("completion tick is sent", () => {
  const body = buildCorrectionBody(ROW, {
    subActivityId: "s", description: "", countColumn: null, count: null,
    lumpsumUnit: null, isCompleted: true,
  });
  assert.equal(body.is_completed, true);
});

test("correction keeps project and other counts, sets the main count", () => {
  const body = buildCorrectionBody(ROW, {
    subActivityId: "s2", description: "  fixed  ", countColumn: "tags_count",
    count: 40, lumpsumUnit: null,
  });
  assert.equal(body.project_id, "p1");
  assert.equal(body.manual_project_code, "P1");
  assert.equal(body.sub_activity_id, "s2");
  assert.equal(body.description, "fixed");
  assert.equal(body.tags_count, 40);
  assert.equal(body.docs_count, 2);
  assert.equal(body.records_count, 0);
  assert.equal(body.count_field, undefined);
});

test("lumpsum correction sends the unit/count pair, and nothing when empty", () => {
  const withCount = buildCorrectionBody(ROW, {
    subActivityId: "s3", description: "", countColumn: null, count: 12, lumpsumUnit: "pages",
  });
  assert.equal(withCount.count_field, "pages");
  assert.equal(withCount.count_value, 12);
  const empty = buildCorrectionBody(ROW, {
    subActivityId: "s3", description: "", countColumn: null, count: null, lumpsumUnit: "pages",
  });
  assert.equal(empty.count_field, undefined);
});

test("normal row before or after submit shows nothing", () => {
  assert.equal(reworkRowBadge(false, null), null);
  assert.equal(reworkRowBadge(false, undefined), null);
});

test("configured row before submit says PM approval is required", () => {
  assert.deepEqual(reworkRowBadge(true, null), {
    label: PM_APPROVAL_REQUIRED_LABEL,
    tone: "warning",
  });
});

test("submitted states come from the server status", () => {
  assert.equal(reworkRowBadge(true, "pending")?.label, "In Review");
  assert.equal(reworkRowBadge(true, "approved")?.tone, "success");
  assert.equal(reworkRowBadge(true, "rejected")?.label, "Rejected - Action Required");
  // Status wins even if the config was removed after submit.
  assert.equal(reworkRowBadge(false, "pending")?.label, "In Review");
});

test("a cancelled cycle falls back to the configuration", () => {
  assert.equal(reworkRowBadge(true, "cancelled")?.label, PM_APPROVAL_REQUIRED_LABEL);
  assert.equal(reworkRowBadge(false, "cancelled"), null);
});
