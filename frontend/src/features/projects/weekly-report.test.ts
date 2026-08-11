/**
 * Weekly Report presentation logic — the cells the Head actually reads.
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So these tests pin the pure module the tab renders from — every
 * formatting rule, the cycle selection and the download gate — rather than
 * mounting the component.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  VALUE_NOT_APPLICABLE,
  WEEKLY_REPORT_COLUMNS,
  WEEKLY_REPORT_CYCLES,
  WEEKLY_REPORT_DEFAULT_CYCLE,
  WEEKLY_REPORT_CYCLE_LABEL,
  WEEKLY_REPORT_WEEK_OFFSETS,
  buildWeeklyReportRows,
  canDownloadWeeklyReport,
  formatBenchmarkCell,
  formatCountCell,
  formatReportDate,
  resolveWeeklyReportCycle,
  weeklyReportCycleForOffset,
  weeklyReportExportPath,
  weeklyReportPath,
  weeklyReportWeekOffset,
  type WeeklyReportApiRow,
} from "./weekly-report.ts";

function apiRow(over: Partial<WeeklyReportApiRow> = {}): WeeklyReportApiRow {
  return {
    report_date: "2026-08-10",
    work_period: "full_day",
    work_period_label: "Full Day",
    employee_name: "Alice Anand",
    project_code: "4716-LC25102900",
    activity_name: "FMTL",
    sub_activity_name: "FMTL-TAG DESCRIPTION FROM P&ID",
    benchmark: 300,
    benchmark_label: null,
    tags: 250,
    docs: null,
    bom: null,
    spares: null,
    pages: null,
    records: null,
    task_status: null,
    task_status_label: null,
    remarks: "FAHN MTL 250 TAGS",
    ...over,
  };
}

// ---------- cycle selection -------------------------------------------------
test("the tab opens on the current week", () => {
  assert.equal(WEEKLY_REPORT_DEFAULT_CYCLE, "current");
  assert.equal(resolveWeeklyReportCycle(null), "current");
  assert.equal(resolveWeeklyReportCycle(undefined), "current");
});

test("only the two supported cycles exist, nearest week first", () => {
  assert.deepEqual(
    WEEKLY_REPORT_CYCLES.map((c) => c.value),
    ["current", "previous"],
  );
  assert.deepEqual(
    WEEKLY_REPORT_CYCLES.map((c) => c.label),
    ["Current week", "Previous week"],
  );
});

test("the selector speaks week offsets, the API speaks cycle names", () => {
  // The shared cycle control (Employee Performance and this tab use the same
  // one) is driven by whole-weeks-back offsets; the weekly-report API takes
  // "current"/"previous". These two functions are the only bridge, so a
  // round-trip must be lossless in both directions.
  assert.deepEqual(WEEKLY_REPORT_WEEK_OFFSETS, [0, 1]);
  assert.equal(WEEKLY_REPORT_CYCLE_LABEL[0], "Current week");
  assert.equal(WEEKLY_REPORT_CYCLE_LABEL[1], "Previous week");

  assert.equal(weeklyReportWeekOffset("current"), 0);
  assert.equal(weeklyReportWeekOffset("previous"), 1);
  assert.equal(weeklyReportCycleForOffset(0), "current");
  assert.equal(weeklyReportCycleForOffset(1), "previous");

  // The backend offers no third cycle, so an out-of-range offset must fall back
  // rather than build a request that comes back 422.
  assert.equal(weeklyReportCycleForOffset(2), "current");
});

test("a hand-typed cycle falls back rather than firing a 422", () => {
  assert.equal(resolveWeeklyReportCycle("previous"), "previous");
  assert.equal(resolveWeeklyReportCycle("last-month"), "current");
  assert.equal(resolveWeeklyReportCycle("Current"), "current");
  assert.equal(resolveWeeklyReportCycle(3), "current");
});

// ---------- dates -----------------------------------------------------------
test("dates format without going through the browser timezone", () => {
  // new Date("2026-08-07") is UTC midnight and renders as the 6th anywhere
  // behind UTC — every date in the report would silently shift by a day.
  assert.equal(formatReportDate("2026-08-07"), "07 Aug 2026");
  assert.equal(formatReportDate("2026-01-01"), "01 Jan 2026");
  assert.equal(formatReportDate("2026-12-31"), "31 Dec 2026");
});

test("an unusable date reads as the placeholder, never as Invalid Date", () => {
  assert.equal(formatReportDate(null), VALUE_NOT_APPLICABLE);
  assert.equal(formatReportDate(""), VALUE_NOT_APPLICABLE);
  assert.equal(formatReportDate("not-a-date"), VALUE_NOT_APPLICABLE);
  assert.equal(formatReportDate("2026-13-01"), VALUE_NOT_APPLICABLE);
});

// The cycle's own date range is no longer formatted here: it is rendered inside
// the shared cycle selector ("AUG 7–13 · Fri–Thu"), which is the one place a
// week's dates are stated. There used to be a second, differently formatted
// line under the control saying the same thing.

// ---------- counts ----------------------------------------------------------
test("a reported count renders as a number", () => {
  assert.equal(formatCountCell(250), "250");
  assert.equal(formatCountCell(1200), "1,200");
});

test("a count of zero is shown, not hidden", () => {
  // 0 arrives only when the row's benchmark measures that unit — a genuine
  // "zero completed against the target", which the Head must see.
  assert.equal(formatCountCell(0), "0");
});

test("an inapplicable unit is a dash, never a zero", () => {
  assert.equal(formatCountCell(null), VALUE_NOT_APPLICABLE);
  assert.equal(formatCountCell(undefined), VALUE_NOT_APPLICABLE);
  assert.equal(formatCountCell(NaN), VALUE_NOT_APPLICABLE);
  assert.equal(formatCountCell("250"), VALUE_NOT_APPLICABLE);
  assert.notEqual(formatCountCell(null), "0");
});

// ---------- benchmark -------------------------------------------------------
test("a numeric benchmark renders as its number", () => {
  assert.equal(formatBenchmarkCell(apiRow({ benchmark: 300 })), "300");
  // A half-day effective target keeps its real value.
  assert.equal(formatBenchmarkCell(apiRow({ benchmark: 150 })), "150");
  // ...and never grows a trailing .00.
  assert.equal(formatBenchmarkCell(apiRow({ benchmark: 150.0 })), "150");
  assert.equal(formatBenchmarkCell(apiRow({ benchmark: 12.5 })), "12.5");
});

test("a completion-only task shows its existing label, not a fake number", () => {
  const row = apiRow({ benchmark: null, benchmark_label: "Lump Sum" });
  assert.equal(formatBenchmarkCell(row), "Lump Sum");
});

test("a non-benchmark activity shows a dash, and its row still exists", () => {
  const row = apiRow({ benchmark: null, benchmark_label: null });
  assert.equal(formatBenchmarkCell(row), VALUE_NOT_APPLICABLE);
  assert.equal(buildWeeklyReportRows([row]).length, 1);
});

// ---------- rows ------------------------------------------------------------
test("a tag row renders every column it should", () => {
  const [row] = buildWeeklyReportRows([apiRow()]);
  assert.equal(row.date, "10 Aug 2026");
  assert.equal(row.workPeriod, "Full Day");
  assert.equal(row.employee, "Alice Anand");
  assert.equal(row.activity, "FMTL");
  assert.equal(row.subActivity, "FMTL-TAG DESCRIPTION FROM P&ID");
  assert.equal(row.benchmark, "300");
  assert.equal(row.tags, "250");
  assert.equal(row.remarks, "FAHN MTL 250 TAGS");
  // The units this row does not measure stay blank.
  assert.deepEqual(
    [row.docs, row.bom, row.spares, row.pages, row.records],
    Array(5).fill(VALUE_NOT_APPLICABLE),
  );
  assert.equal(row.taskStatus, VALUE_NOT_APPLICABLE);
});

test("the Project column is the code alone", () => {
  const [row] = buildWeeklyReportRows([apiRow()]);
  assert.equal(row.project, "4716-LC25102900");
  // Nothing in the row carries a project name.
  assert.equal(
    Object.values(row).some((v) => String(v).includes("Execution of Various")),
    false,
  );
});

test("Activity and Sub-Activity stay two separate cells", () => {
  const [row] = buildWeeklyReportRows([apiRow()]);
  assert.notEqual(row.activity, row.subActivity);
  assert.equal(row.subActivity.includes(row.activity + " / "), false);
});

test("a task row shows its status and no invented counts", () => {
  const [row] = buildWeeklyReportRows([
    apiRow({
      sub_activity_name: "TOOL SUPPORT-ENVIRONMENT SETUP",
      benchmark: null,
      benchmark_label: "Lump Sum",
      tags: null,
      task_status: "IN_PROGRESS",
      task_status_label: "In progress",
    }),
  ]);
  assert.equal(row.taskStatus, "In progress");
  assert.equal(row.benchmark, "Lump Sum");
  assert.deepEqual(
    [row.tags, row.docs, row.bom, row.spares, row.pages, row.records],
    Array(6).fill(VALUE_NOT_APPLICABLE),
  );
});

test("a docs row reports docs and leaves tags blank", () => {
  const [row] = buildWeeklyReportRows([
    apiRow({ tags: null, docs: 15, benchmark: 20 }),
  ]);
  assert.equal(row.docs, "15");
  assert.equal(row.tags, VALUE_NOT_APPLICABLE);
});

test("a split day keeps its half, and never reads as a full day", () => {
  const rows = buildWeeklyReportRows([
    apiRow({ work_period: "first_half", work_period_label: "First Half" }),
    apiRow({ work_period: "second_half", work_period_label: "Second Half" }),
  ]);
  assert.deepEqual(
    rows.map((r) => r.workPeriod),
    ["First Half", "Second Half"],
  );
  assert.equal(rows.some((r) => r.workPeriod === "Full Day"), false);
});

test("the server's order is preserved exactly", () => {
  // Re-sorting here is the one way the screen and the downloaded file could
  // end up disagreeing.
  const rows = buildWeeklyReportRows([
    apiRow({ report_date: "2026-08-12", employee_name: "Zara Zaman" }),
    apiRow({ report_date: "2026-08-10", employee_name: "Alice Anand" }),
    apiRow({ report_date: "2026-08-11", employee_name: "Bala Murugan" }),
  ]);
  assert.deepEqual(
    rows.map((r) => r.employee),
    ["Zara Zaman", "Alice Anand", "Bala Murugan"],
  );
});

test("every row key is unique, even for two identical lines", () => {
  const rows = buildWeeklyReportRows([apiRow(), apiRow(), apiRow()]);
  assert.equal(new Set(rows.map((r) => r.key)).size, 3);
});

test("an empty or missing payload produces no rows rather than throwing", () => {
  assert.deepEqual(buildWeeklyReportRows([]), []);
  assert.deepEqual(buildWeeklyReportRows(null), []);
  assert.deepEqual(buildWeeklyReportRows(undefined), []);
});

test("a blank text field never renders as an empty cell", () => {
  const [row] = buildWeeklyReportRows([
    apiRow({ activity_name: null, sub_activity_name: "  ", remarks: "" }),
  ]);
  assert.equal(row.activity, VALUE_NOT_APPLICABLE);
  assert.equal(row.subActivity, VALUE_NOT_APPLICABLE);
  assert.equal(row.remarks, VALUE_NOT_APPLICABLE);
});

// ---------- columns ---------------------------------------------------------
test("the table columns are the agreed ones, in the export's order", () => {
  assert.deepEqual(
    WEEKLY_REPORT_COLUMNS.map((c) => c.label),
    [
      "Date", "Work Period", "Employee", "Project", "Activity", "Sub-Activity",
      "Benchmark", "Tags", "Docs", "BOM", "Spares", "Pages", "Records",
      "Task Status", "Remarks",
    ],
  );
});

test("every column has a value on every built row", () => {
  const [row] = buildWeeklyReportRows([apiRow()]);
  for (const col of WEEKLY_REPORT_COLUMNS) {
    const value = row[col.key as keyof typeof row];
    assert.equal(typeof value, "string", col.key);
    assert.notEqual(value, "", col.key);
  }
});

test("the long free-text columns are the ones marked to wrap", () => {
  const wrapped = WEEKLY_REPORT_COLUMNS.filter((c) => c.wrap).map((c) => c.key);
  assert.deepEqual(wrapped, ["activity", "subActivity", "remarks"]);
});

// ---------- preview and download ask for the same week ----------------------
test("the preview and the export paths carry the SELECTED cycle", () => {
  assert.equal(
    weeklyReportPath("p1", "previous"),
    "/projects/p1/weekly-report?cycle=previous",
  );
  assert.equal(
    weeklyReportExportPath("p1", "previous"),
    "/projects/p1/weekly-report.xlsx?cycle=previous",
  );
  assert.equal(
    weeklyReportExportPath("p1", "current"),
    "/projects/p1/weekly-report.xlsx?cycle=current",
  );
});

test("downloading while Previous Week is shown never asks for the current week", () => {
  // The exact regression the two paths exist to prevent: nothing would error,
  // the file would simply describe the wrong week.
  const shown = resolveWeeklyReportCycle("previous");
  assert.equal(weeklyReportExportPath("p1", shown).includes("cycle=previous"), true);
  assert.equal(weeklyReportExportPath("p1", shown).includes("cycle=current"), false);
});

test("the two paths differ only by the .xlsx suffix, for every cycle", () => {
  for (const { value } of WEEKLY_REPORT_CYCLES) {
    assert.equal(
      weeklyReportExportPath("p1", value),
      weeklyReportPath("p1", value).replace("weekly-report?", "weekly-report.xlsx?"),
    );
  }
});

// ---------- the download gate ----------------------------------------------
test("Download is available once the week has rows", () => {
  assert.equal(canDownloadWeeklyReport([apiRow()], false), true);
});

test("Download is disabled while loading and on an empty week", () => {
  assert.equal(canDownloadWeeklyReport([apiRow()], true), false);
  assert.equal(canDownloadWeeklyReport([], false), false);
  assert.equal(canDownloadWeeklyReport(null, false), false);
  assert.equal(canDownloadWeeklyReport(undefined, false), false);
});
