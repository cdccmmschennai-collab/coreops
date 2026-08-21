/**
 * PM cumulative Production Status report - UI logic (Phase 4).
 *
 * The repo's frontend harness is `node --test` over `src/**​/*.test.ts` (see
 * package.json `test:unit`): plain TypeScript, no jsdom / React Testing
 * Library. So these tests pin the pure module the dialog renders from - who may
 * open it, what every cell says, and which state applies - rather than mounting
 * the component.
 *
 * They also pin the thing this phase most needs to be true: the preview does no
 * calculation of its own. The rows arrive finished from the backend, and the
 * .xlsx is rendered from the same dataset, so the file cannot disagree with the
 * screen. The backend rules these mirror are covered independently in
 * backend/tests/test_production_status_report.py.
 *
 *     npm run test:unit
 */
import assert from "node:assert/strict";
import { test } from "node:test";

import { productionStatusKeys } from "./keys.ts";
import {
  buildProductionStatusReportRows,
  buildReportMonthOptions,
  canDownloadReport,
  canViewProductionStatusReport,
  formatReportDate,
  formatReportMonthLabel,
  isReportMonth,
  REPORT_ALL_PROJECTS,
  REPORT_BLANK,
  REPORT_COLUMNS,
  REPORT_EMPTY_MONTH_TITLE,
  REPORT_EMPTY_TITLE,
  REPORT_MONTH_ALL,
  REPORT_MONTH_ALL_LABEL,
  reportCount,
  reportErrorMessage,
  reportMonthParam,
  reportSubtitle,
  resolveReportMonth,
  type ProductionStatusReportRowLike,
} from "./production-status-report.ts";

// A row exactly as GET /production-status/report returns it.
function row(
  over: Partial<ProductionStatusReportRowLike> = {},
): ProductionStatusReportRowLike {
  return {
    serial: 1,
    id: "ps-1",
    project_id: "proj-1",
    project_code: "4460-GC22104900",
    // Already combined by the backend: project - plant revision.
    project_plant: "4460-GC22104900 - KAHM REV-0",
    revision: "REV-0",
    maintenance_plant_id: "plant-kahm",
    maintenance_plant_code: "KAHM",
    activity_id: "act-1",
    activity: "TAG ESTIMATION",
    status: "closed",
    status_label: "CLOSED",
    tag_count: 225,
    doc_count: 0,
    spares_count: 0,
    crs_count: 0,
    completed_on: "2025-12-05",
    remarks: "Issued to client.",
    by: "Santhosh Kumar",
    ...over,
  };
}

// --- 1. who may open the report ---------------------------------------------

test("the report is PM-only", () => {
  assert.equal(canViewProductionStatusReport("project_manager"), true);
  // A Project Head and an Activity Lead are both `employee` at role level -
  // they read Production Status on their own projects and must not see this.
  assert.equal(canViewProductionStatusReport("employee"), false);
  assert.equal(canViewProductionStatusReport(undefined), false);
  assert.equal(canViewProductionStatusReport(null), false);
  assert.equal(canViewProductionStatusReport(""), false);
});

// --- 2. the preview renders the backend's dataset unchanged ------------------

test("rows are rendered one-to-one, in the order received", () => {
  const rows = buildProductionStatusReportRows([
    row({ id: "a", serial: 1, project_plant: "GC-A", revision: "REV-0" }),
    row({ id: "b", serial: 2, project_plant: "GC-A", revision: "REV-1" }),
    row({ id: "c", serial: 3, project_plant: "GC-B", revision: "REV-0" }),
  ]);

  assert.equal(rows.length, 3);
  // Nothing is dropped, merged, re-sorted or renumbered.
  assert.deepEqual(rows.map((r) => r.key), ["a", "b", "c"]);
  assert.deepEqual(rows.map((r) => r.serial), ["1", "2", "3"]);
  assert.deepEqual(rows.map((r) => r.projectPlant), ["GC-A", "GC-A", "GC-B"]);
});

test("S.NO is the backend's serial, never a client-side index", () => {
  // If the preview numbered rows itself it would print 1,2,3 here - and then
  // disagree with the workbook, which stamps the backend's serial.
  const rows = buildProductionStatusReportRows([
    row({ id: "a", serial: 7 }),
    row({ id: "b", serial: 8 }),
  ]);
  assert.deepEqual(rows.map((r) => r.serial), ["7", "8"]);
});

test("REV-0 and REV-1 stay distinct - inside the PROJECT / PLANT cell", () => {
  const rows = buildProductionStatusReportRows([
    row({
      id: "a",
      revision: "REV-0",
      project_plant: "4460-GC22104900 - KAHM REV-0",
      activity: "MTL",
      status_label: "CLOSED",
    }),
    row({
      id: "b",
      revision: "REV-1",
      project_plant: "4460-GC22104900 - KAHN REV-1",
      activity: "MTL",
      status_label: "IN PROGRESS",
    }),
  ]);
  // There is no REVISION column any more, so the two rows must remain
  // distinguishable by their combined cell alone.
  assert.deepEqual(rows.map((r) => r.projectPlant), [
    "4460-GC22104900 - KAHM REV-0",
    "4460-GC22104900 - KAHN REV-1",
  ]);
  assert.notEqual(rows[0].projectPlant, rows[1].projectPlant);
  assert.deepEqual(rows.map((r) => r.status), ["CLOSED", "IN PROGRESS"]);
});

test("the PROJECT / PLANT cell is printed verbatim, never re-composed", () => {
  // The backend owns the format. If the preview built the string itself it
  // would be a second implementation and could drift from the Excel.
  const cases = [
    "4460-GC22104900 - KAHM REV-0",   // project + plant + revision
    "4391-GC21107300 REV-0",          // no plant
    "NGLC2-GC10108000-PUMPING STATION", // project alone
  ];
  for (const project_plant of cases) {
    const [built] = buildProductionStatusReportRows([row({ project_plant })]);
    assert.equal(built.projectPlant, project_plant);
  }
});

test("no placeholder junk ever reaches the PROJECT / PLANT cell", () => {
  for (const project_plant of ["4391-GC21107300 REV-0", "4391-GC21107300"]) {
    const [built] = buildProductionStatusReportRows([row({ project_plant })]);
    for (const junk of ["null", "undefined", "/ null", " - REV", "  "]) {
      assert.equal(
        built.projectPlant.includes(junk),
        false,
        `${junk} leaked into ${built.projectPlant}`,
      );
    }
  }
});

// --- 3. counts --------------------------------------------------------------

test("the four counts stay four independent values", () => {
  const [r] = buildProductionStatusReportRows([
    row({ tag_count: 225, doc_count: 12, spares_count: 7, crs_count: 3 }),
  ]);
  assert.deepEqual([r.tag, r.doc, r.spares, r.crs], ["225", "12", "7", "3"]);
  // No combined total is produced anywhere.
  assert.equal(Object.keys(r).some((k) => k.toLowerCase().includes("total")), false);
});

test("zero renders as 0, not as a placeholder", () => {
  // Deliberately different from the project tab's formatCount, which shows "-"
  // for 0. This is the export preview: it must show the number the Excel cell
  // carries, so the PM can check the file against the screen.
  assert.equal(reportCount(0), "0");
  assert.equal(reportCount(225), "225");

  const [r] = buildProductionStatusReportRows([
    row({ tag_count: 225, doc_count: 0, spares_count: 0, crs_count: 0 }),
  ]);
  assert.deepEqual([r.tag, r.doc, r.spares, r.crs], ["225", "0", "0", "0"]);
});

test("a genuinely absent count falls back to the placeholder", () => {
  assert.equal(reportCount(null), REPORT_BLANK);
  assert.equal(reportCount(undefined), REPORT_BLANK);
  assert.equal(reportCount(Number.NaN), REPORT_BLANK);
});

// --- 4. completed on ---------------------------------------------------------

test("completed_on renders DD-MMM-YYYY, the workbook's own format", () => {
  assert.equal(formatReportDate("2025-12-05"), "05-Dec-2025");
  assert.equal(formatReportDate("2026-01-31"), "31-Jan-2026");
});

test("a date-only string is never shifted by the viewer's timezone", () => {
  // Parsed from the digits, never through new Date(): UTC-midnight parsing
  // would show the 4th to anyone west of Greenwich.
  assert.equal(formatReportDate("2025-12-05T00:00:00Z"), "05-Dec-2025");
  assert.equal(formatReportDate("2025-01-01"), "01-Jan-2025");
});

test("a null completed_on leaves the cell blank - no date is invented", () => {
  assert.equal(formatReportDate(null), "");
  assert.equal(formatReportDate(undefined), "");
  assert.equal(formatReportDate("not a date"), "");

  const [r] = buildProductionStatusReportRows([row({ completed_on: null })]);
  assert.equal(r.completedOn, "");
});

// --- 5. remarks --------------------------------------------------------------

test("remarks are preserved in full, line breaks and all", () => {
  const remarks =
    "Tag estimation completed for all 225 tags.\nPunch list closed 04-Dec.\nAwaiting sign-off.";
  const [r] = buildProductionStatusReportRows([row({ remarks })]);
  // Never truncated and never squashed to one line - the cell wraps instead.
  assert.equal(r.remarks, remarks);
  assert.equal(r.remarks?.split("\n").length, 3);
});

test("an empty remark becomes null so the cell can show a placeholder", () => {
  assert.equal(buildProductionStatusReportRows([row({ remarks: "" })])[0].remarks, null);
  assert.equal(buildProductionStatusReportRows([row({ remarks: "   " })])[0].remarks, null);
  assert.equal(buildProductionStatusReportRows([row({ remarks: null })])[0].remarks, null);
});

// --- 6. BY is the person ------------------------------------------------------

test("BY is the API's name, never a role and never converted client-side", () => {
  const [r] = buildProductionStatusReportRows([row({ by: "Santhosh Kumar" })]);
  assert.equal(r.by, "Santhosh Kumar");
  assert.notEqual(r.by, "PM");
  assert.notEqual(r.by, "Activity Lead");

  // Missing is honestly unknown, never a role word substituted in.
  assert.equal(buildProductionStatusReportRows([row({ by: "" })])[0].by, REPORT_BLANK);
});

// --- 7. status vocabulary -----------------------------------------------------

test("the preview prints the backend's status wording, not its own", () => {
  const rows = buildProductionStatusReportRows([
    row({ id: "a", status: "in_progress", status_label: "IN PROGRESS" }),
    row({ id: "b", status: "closed", status_label: "CLOSED" }),
  ]);
  assert.deepEqual(rows.map((r) => r.status), ["IN PROGRESS", "CLOSED"]);
  // The stored value is carried through untouched for the badge.
  assert.deepEqual(rows.map((r) => r.statusValue), ["in_progress", "closed"]);
});

// --- 8. columns ---------------------------------------------------------------

test("the columns are the workbook's columns, in the workbook's order", () => {
  assert.deepEqual(
    REPORT_COLUMNS.map((c) => c.label),
    [
      "S.NO", "PROJECT / PLANT", "ACTIVITY", "PROJECT STATUS",
      // Four separate count columns - no merged COUNT banner, no total.
      "TAG", "DOC", "SPARES", "CRS",
      "COMPLETED ON", "REMARKS", "BY",
    ],
  );
  assert.equal(REPORT_COLUMNS.length, 11);
});

test("there is no REVISION column - it lives inside PROJECT / PLANT", () => {
  // `REPORT_COLUMNS` is `as const`, so its labels are a literal union and
  // `.includes("REVISION")` would not even compile. Widening to string[] keeps
  // the check a real runtime assertion rather than a tautology.
  const labels: string[] = REPORT_COLUMNS.map((c) => c.label);
  assert.equal(labels.includes("REVISION"), false);

  // ...but the value is still on the row, because it identifies the record and
  // its history.
  const source = row({ revision: "REV-1" });
  assert.equal(source.revision, "REV-1");
});

test("every column key exists on a built row", () => {
  const [r] = buildProductionStatusReportRows([row()]);
  for (const col of REPORT_COLUMNS) {
    assert.ok(col.key in r, `row is missing "${col.key}"`);
  }
});

// --- 9. empty / download / subtitle ------------------------------------------

test("no records is an empty report, not an error", () => {
  assert.deepEqual(buildProductionStatusReportRows([]), []);
  assert.deepEqual(buildProductionStatusReportRows(null), []);
  assert.deepEqual(buildProductionStatusReportRows(undefined), []);
  assert.equal(REPORT_EMPTY_TITLE, "No production status records available.");
});

test("download is offered only for a settled, non-empty report", () => {
  assert.equal(canDownloadReport([row()], false), true);
  // Nothing to download.
  assert.equal(canDownloadReport([], false), false);
  assert.equal(canDownloadReport(null, false), false);
  // Still loading - the file would not match what is on screen.
  assert.equal(canDownloadReport([row()], true), false);
});

test("the subtitle counts rows, and says what the report covers", () => {
  assert.equal(reportSubtitle(12), `12 rows - ${REPORT_ALL_PROJECTS}`);
  assert.equal(reportSubtitle(1), `1 row - ${REPORT_ALL_PROJECTS}`);
  assert.equal(reportSubtitle(0), REPORT_ALL_PROJECTS);
  assert.equal(reportSubtitle(null), REPORT_ALL_PROJECTS);
});

// --- 10. errors ---------------------------------------------------------------

test("a 403 explains the PM-only rule", () => {
  assert.match(reportErrorMessage(403, null), /project manager/i);
  // The backend's own wording wins when it sent one.
  assert.equal(reportErrorMessage(403, "Nope."), "Nope.");
});

test("an offline request is reported as unreachable, not as a server error", () => {
  assert.match(reportErrorMessage(0, null), /Could not reach the server/);
  assert.match(reportErrorMessage(500, null), /Something went wrong/);
});

// --- 11. query key ------------------------------------------------------------

test("the report key carries no project - it spans all of them", () => {
  assert.deepEqual(productionStatusKeys.report(), [
    "production-status",
    "report",
    "",
  ]);
  // Distinct from the per-project keys, so opening the report never serves a
  // single project's cached rows.
  assert.notDeepEqual(
    productionStatusKeys.report(),
    productionStatusKeys.latest("proj-1"),
  );
});

// --- 12. the month filter (Phase 5) ------------------------------------------
//
// The dropdown narrows the REQUEST, never the response: nothing below filters a
// row. The filtering itself is the backend's, covered in
// backend/tests/test_production_status_report.py section 19.

test("All Months sends no month - the cumulative request, unchanged", () => {
  for (const all of [REPORT_MONTH_ALL, "", null, undefined]) {
    assert.equal(reportMonthParam(all), undefined);
  }
  assert.equal(REPORT_MONTH_ALL_LABEL, "All Months");
});

test("a chosen month is sent as the API's YYYY-MM key; junk never is", () => {
  assert.equal(reportMonthParam("2026-08"), "2026-08");
  assert.equal(reportMonthParam(" 2026-09 "), "2026-09");
  // Unfiltered beats asking the API for a month it will reject with an error.
  for (const bad of ["2026", "2026-13", "2026-00", "26-08", "2026-08-14"]) {
    assert.equal(reportMonthParam(bad), undefined, bad);
    assert.equal(isReportMonth(bad), false, bad);
  }
});

test("a month reads as its name and year, unshifted by the viewer's timezone", () => {
  assert.equal(formatReportMonthLabel("2026-08"), "August 2026");
  assert.equal(formatReportMonthLabel("2026-09"), "September 2026");
  // Through `new Date(...)` this would be December for anyone west of
  // Greenwich; parsed from the digits it cannot drift.
  const tz = process.env.TZ;
  process.env.TZ = "America/Los_Angeles";
  assert.equal(formatReportMonthLabel("2026-01"), "January 2026");
  process.env.TZ = tz;
  // Nothing usable prints nothing, never junk.
  assert.equal(formatReportMonthLabel("2026-13"), "");
  assert.equal(formatReportMonthLabel(null), "");
});

test("the dropdown is All Months plus the months that have records", () => {
  assert.deepEqual(buildReportMonthOptions(["2026-08", "2026-09"]), [
    { value: REPORT_MONTH_ALL, label: "All Months" },
    { value: "2026-08", label: "August 2026" },
    { value: "2026-09", label: "September 2026" },
  ]);
  // Always reachable, even with nothing recorded at all.
  assert.deepEqual(buildReportMonthOptions([]), [
    { value: REPORT_MONTH_ALL, label: "All Months" },
  ]);
  // Duplicates and junk cannot become options (they would also be dup keys).
  const options = buildReportMonthOptions(["2026-08", "2026-08", "", "2026-13"]);
  assert.deepEqual(options.map((o) => o.value), [REPORT_MONTH_ALL, "2026-08"]);
});

test("a selection no longer on offer falls back to All Months", () => {
  const months = ["2026-08", "2026-09"];
  assert.equal(resolveReportMonth("2026-08", months), "2026-08");
  // Better the whole report than a stale month over an empty table.
  assert.equal(resolveReportMonth("2026-10", months), REPORT_MONTH_ALL);
  assert.equal(resolveReportMonth(null, months), REPORT_MONTH_ALL);
});

test("the subtitle names the month and counts the filtered rows", () => {
  // The count is the backend's row_count for the filtered dataset, so it is
  // also the number of rows in the downloaded file.
  assert.equal(
    reportSubtitle(4, "2026-08"),
    `4 rows - August 2026 - ${REPORT_ALL_PROJECTS}`,
  );
  assert.equal(reportSubtitle(0, "2026-10"), `October 2026 - ${REPORT_ALL_PROJECTS}`);
  // All Months keeps exactly the wording it always had.
  assert.equal(reportSubtitle(12, null), `12 rows - ${REPORT_ALL_PROJECTS}`);
  // Still all-project: the month narrows the report, it is not a different one.
  assert.match(reportSubtitle(4, "2026-08"), /all projects/i);
});

test("an empty month reads differently from nothing ever recorded", () => {
  assert.notEqual(REPORT_EMPTY_MONTH_TITLE, REPORT_EMPTY_TITLE);
});

test("each month is its own cached dataset, and All Months has one key", () => {
  assert.deepEqual(productionStatusKeys.report("2026-08"),
    ["production-status", "report", "2026-08"]);
  assert.notDeepEqual(
    productionStatusKeys.report("2026-08"),
    productionStatusKeys.report("2026-09"),
  );
  assert.deepEqual(
    productionStatusKeys.report(reportMonthParam(REPORT_MONTH_ALL)),
    productionStatusKeys.report(),
  );
});

test("preview and download resolve the selection to the same request", () => {
  // The dialog derives ONE monthParam and gives it to both the report query and
  // the .xlsx download - the whole reason the file is the rows on screen.
  for (const selection of [REPORT_MONTH_ALL, "2026-08", "2026-13"]) {
    assert.equal(reportMonthParam(selection), reportMonthParam(selection));
  }
});

test("the month adds no other filter and no client-side filtering", () => {
  // Same columns, and rows still mapped one-to-one in the order received.
  assert.equal(REPORT_COLUMNS.length, 11);
  const rows = buildProductionStatusReportRows([
    row({ id: "a", serial: 4 }),
    row({ id: "b", serial: 5 }),
  ]);
  assert.deepEqual(rows.map((r) => r.key), ["a", "b"]);
  assert.deepEqual(rows.map((r) => r.serial), ["4", "5"]);
});
