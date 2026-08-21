/**
 * PM cumulative Production Status report - presentation logic (Phase 4).
 *
 * Everything the preview dialog decides - who may open it, what every cell
 * says, which state applies, how a failure reads - is decided here, and the
 * component only renders the result. Same split as `production-status.ts`: the
 * repo's `node --test` harness has no jsdom or React Testing Library, so logic
 * living inside JSX cannot be covered at all.
 *
 * This module computes NOTHING about the report itself. It does not sort,
 * filter, number, sum or re-derive anything - including the Phase 5 month
 * filter, which is a query parameter sent to the backend and never a pass over
 * rows here. What lives in this file is only how a month is spelled ("2026-08"),
 * how it reads ("August 2026") and which options exist; the FILTERING happens in
 * the report query, so the preview and the .xlsx download stay one dataset. The
 * backend
 * (`production_status/service.py::cumulative_report`) is the one place the
 * dataset exists: it picks the latest row per project + revision + activity,
 * orders them, stamps `serial`, resolves the plant label, the activity label,
 * the status wording and the author's name. The rows arrive finished, and the
 * .xlsx endpoint renders the very same rows - which is what makes "the Excel
 * contains exactly the preview dataset" a structural fact rather than a promise
 * two code paths have to keep.
 *
 * Deliberately dependency-free (like production-status.ts, scope.ts, tabs.ts)
 * so `node --test` can cover it without a bundler. The interface below is a
 * structural stand-in for the generated openapi type - TypeScript matches by
 * shape, so API objects pass straight in.
 */

// ---------------------------------------------------------------------------
// Who may open the report
// ---------------------------------------------------------------------------

/**
 * The report is PM-only.
 *
 * Deliberately a ROLE check and not the `project.manage` capability: this is
 * not a permission to change projects, it is "may you see every project's
 * production at once". A Project Head and an Activity Lead both have
 * project-scoped read authority on the Production Status tab and still must not
 * see this - which is exactly the distinction
 * `service._assert_can_read_report` draws on the server.
 *
 * Hiding the button is convenience, never the control. The endpoint re-resolves
 * the same rule and answers 403 regardless of what this returns.
 */
export function canViewProductionStatusReport(
  role: string | null | undefined,
): boolean {
  return role === "project_manager";
}

// ---------------------------------------------------------------------------
// Rows
// ---------------------------------------------------------------------------

/** One report row, as GET /production-status/report returns it. */
export interface ProductionStatusReportRowLike {
  serial: number;
  id: string;
  project_id: string;
  project_code: string;
  project_plant: string;
  /** Still on the row, but folded into `project_plant` for display. */
  revision: string;
  maintenance_plant_id?: string | null;
  maintenance_plant_code?: string | null;
  /** Null when the activity was typed rather than chosen from Activity Master. */
  activity_id?: string | null;
  /** The rendered ACTIVITY cell - resolved server-side either way. */
  activity: string;
  status: string;
  status_label: string;
  tag_count: number;
  doc_count: number;
  spares_count: number;
  crs_count: number;
  completed_on?: string | null;
  remarks?: string | null;
  by: string;
}

/**
 * Stands in for a value the record genuinely does not carry - a missing author
 * name, an activity that resolved to nothing. A visible placeholder rather than
 * a blank cell, which reads as "this column does not apply here".
 *
 * NEVER used for a count. See `reportCount`.
 */
export const REPORT_BLANK = "-";

export interface ProductionStatusReportTableRow {
  key: string;
  serial: string;
  /** Project, Maintenance Plant and revision, already combined by the backend. */
  projectPlant: string;
  activity: string;
  status: string;
  /** The raw stored status, so the badge can colour without re-parsing a label. */
  statusValue: string;
  tag: string;
  doc: string;
  spares: string;
  crs: string;
  completedOn: string;
  /** Raw remarks - rendered with whitespace preserved, never trimmed to one line. */
  remarks: string | null;
  by: string;
}

/**
 * A count for the report preview.
 *
 * Zero renders as "0", NOT as the "-" the project tab uses. The two screens are
 * answering different questions: on the tab a 0 means "this unit was not part
 * of the update", while the report is the thing the PM exports to a spreadsheet
 * and sums - so the preview shows the same numeric 0 the Excel cell carries.
 * A reader must be able to check the file against the screen and see the same
 * figures.
 */
export function reportCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return REPORT_BLANK;
  }
  return String(Math.round(value));
}

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

/**
 * `completed_on` ("2025-12-05") as "05-Dec-2025" - the same DD-MMM-YYYY the
 * workbook's COMPLETED ON column is formatted with, so the screen and the file
 * read identically.
 *
 * Parsed from the digits, never through `new Date(...)`: a date-only string is
 * parsed as UTC midnight by the JS Date constructor, so any viewer west of
 * Greenwich would see the previous day. Same reasoning as
 * `production-status.ts::formatProductionDate` and `lib/format.ts::parseWallClock`.
 *
 * A null date returns "" - an empty cell, matching the workbook, because no
 * date is invented for an update that has not completed.
 */
export function formatReportDate(raw: string | null | undefined): string {
  if (!raw) return "";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(raw);
  if (!m) return "";
  const month = MONTHS[Number(m[2]) - 1];
  if (!month) return "";
  return `${m[3]}-${month}-${m[1]}`;
}

/**
 * Turn API rows into table rows.
 *
 * A straight one-to-one mapping in the order received. Nothing is dropped,
 * merged, re-sorted or renumbered - `serial` is the backend's, so the S.NO on
 * screen is the S.NO in the file.
 */
export function buildProductionStatusReportRows(
  rows: readonly ProductionStatusReportRowLike[] | null | undefined,
): ProductionStatusReportTableRow[] {
  return (rows ?? []).map((r) => ({
    key: r.id,
    serial: String(r.serial),
    // Project + Maintenance Plant + revision, combined server-side and already
    // guaranteed clean - no "null", no "undefined", no dangling separator. The
    // preview prints it verbatim, which is why it always matches the Excel.
    projectPlant: r.project_plant || REPORT_BLANK,
    activity: r.activity || REPORT_BLANK,
    // The backend's wording of the existing vocabulary - the preview never
    // maps in_progress/closed to words itself, or the file could disagree.
    status: r.status_label || r.status || REPORT_BLANK,
    statusValue: r.status,
    // Four independent units, each carried through on its own. Never summed.
    tag: reportCount(r.tag_count),
    doc: reportCount(r.doc_count),
    spares: reportCount(r.spares_count),
    crs: reportCount(r.crs_count),
    completedOn: formatReportDate(r.completed_on),
    // Kept whole. The cell wraps; the text is never cut.
    remarks: r.remarks && r.remarks.trim() !== "" ? r.remarks : null,
    // The real person, straight from the API. Never a role word, and never
    // converted from one client-side.
    by: r.by?.trim() || REPORT_BLANK,
  }));
}

// ---------------------------------------------------------------------------
// Columns
// ---------------------------------------------------------------------------

/**
 * The preview's columns, in the workbook's order.
 *
 * TAG / DOC / SPARES / CRS are four separate columns under no merged "COUNT"
 * banner: they are four independent units and there is no combined total,
 * here or in the file.
 *
 * There is deliberately NO REVISION column: the revision is part of the
 * PROJECT / PLANT cell ("4460-GC22104900 - KAHM REV-0"), which is the
 * business's own way of naming a project revision. The value is still on every
 * row (`ProductionStatusReportRowLike.revision`) because it identifies the
 * record and its history — it just has no column of its own, in the preview or
 * in the file.
 */
export const REPORT_COLUMNS = [
  { key: "serial", label: "S.NO", numeric: true },
  { key: "projectPlant", label: "PROJECT / PLANT", numeric: false },
  { key: "activity", label: "ACTIVITY", numeric: false },
  { key: "status", label: "PROJECT STATUS", numeric: false },
  { key: "tag", label: "TAG", numeric: true },
  { key: "doc", label: "DOC", numeric: true },
  { key: "spares", label: "SPARES", numeric: true },
  { key: "crs", label: "CRS", numeric: true },
  { key: "completedOn", label: "COMPLETED ON", numeric: false },
  { key: "remarks", label: "REMARKS", numeric: false },
  { key: "by", label: "BY", numeric: false },
] as const;

// ---------------------------------------------------------------------------
// Download
// ---------------------------------------------------------------------------

/** True when there is something worth downloading and nothing in flight. */
export function canDownloadReport(
  rows: readonly ProductionStatusReportRowLike[] | null | undefined,
  isFetching: boolean,
): boolean {
  return !isFetching && (rows?.length ?? 0) > 0;
}

/**
 * Sub-line under the dialog title: "12 rows - all projects", or
 * "4 rows - August 2026 - all projects" once a month is chosen.
 *
 * The count is the BACKEND's `row_count`, which always describes the rows it
 * sent - so the number on screen is the number of rows in the file. Nothing
 * here counts anything itself.
 */
export function reportSubtitle(
  count: number | null | undefined,
  month?: string | null,
): string {
  const label = monthLabel(month);
  const scope = label ? `${label} - ${REPORT_ALL_PROJECTS}` : REPORT_ALL_PROJECTS;
  if (count === null || count === undefined || count <= 0) {
    return scope;
  }
  return `${count} ${count === 1 ? "row" : "rows"} - ${scope}`;
}

// ---------------------------------------------------------------------------
// The month filter (Phase 5)
// ---------------------------------------------------------------------------

/**
 * The "no month" sentinel.
 *
 * A non-empty string on purpose: the underlying Radix Select reserves "" for
 * its own placeholder/clear behaviour, so an empty value cannot be an option.
 * It is turned back into "no query parameter at all" by `reportMonthParam`.
 */
export const REPORT_MONTH_ALL = "all";

export const REPORT_MONTH_ALL_LABEL = "All Months";
export const REPORT_MONTH_FIELD_LABEL = "Month";

/**
 * The value the API should be asked for.
 *
 * "all" (and anything blank or malformed) becomes `undefined`, i.e. no `month`
 * parameter - which is exactly the cumulative all-months request this dialog
 * has always made. Both the preview and the .xlsx download go through this one
 * function, so they cannot ask for different things.
 */
export function reportMonthParam(
  value: string | null | undefined,
): string | undefined {
  const clean = (value ?? "").trim();
  if (!clean || clean === REPORT_MONTH_ALL) return undefined;
  return isReportMonth(clean) ? clean : undefined;
}

/** Is this a month key the API will accept - "2026-08"? */
export function isReportMonth(value: string | null | undefined): boolean {
  return /^\d{4}-(0[1-9]|1[0-2])$/.test((value ?? "").trim());
}

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;

/**
 * "2026-08" as "August 2026".
 *
 * Formatted from the digits rather than through `new Date(...)`/`toLocale...`:
 * a month key is not an instant, and constructing a Date from one would put it
 * at UTC midnight, which is the previous month for any viewer west of
 * Greenwich. Same reasoning as `formatReportDate`.
 *
 * Anything that is not a month key returns "" - the caller then falls back to
 * the all-months wording rather than printing something meaningless.
 */
export function formatReportMonthLabel(value: string | null | undefined): string {
  const clean = (value ?? "").trim();
  if (!isReportMonth(clean)) return "";
  const name = MONTH_NAMES[Number(clean.slice(5, 7)) - 1];
  return name ? `${name} ${clean.slice(0, 4)}` : "";
}

/** The label for a selection, or "" for All Months. Internal to this module. */
function monthLabel(value: string | null | undefined): string {
  return formatReportMonthLabel(reportMonthParam(value) ?? "");
}

export interface ReportMonthOption {
  value: string;
  label: string;
}

/**
 * The Month dropdown's options: All Months first, then every month that has
 * records.
 *
 * The months come from the API (`ProductionStatusReportOut.months`), derived
 * there from the production status records themselves - this never invents a
 * range, and never offers a month with nothing in it. Unrecognised entries from
 * a newer backend are skipped rather than rendered as junk, and duplicates
 * collapse so a repeated month cannot produce two identical options (which
 * would also be duplicate React keys).
 *
 * `All Months` is always present, so the PM can always get back to the
 * cumulative report - including when there are no records at all.
 */
export function buildReportMonthOptions(
  months: readonly string[] | null | undefined,
): ReportMonthOption[] {
  const seen = new Set<string>();
  const options: ReportMonthOption[] = [
    { value: REPORT_MONTH_ALL, label: REPORT_MONTH_ALL_LABEL },
  ];
  for (const raw of months ?? []) {
    const month = (raw ?? "").trim();
    if (!isReportMonth(month) || seen.has(month)) continue;
    seen.add(month);
    options.push({ value: month, label: formatReportMonthLabel(month) });
  }
  return options;
}

/**
 * Keep a selection that is still on offer; otherwise fall back to All Months.
 *
 * Guards the one way this dropdown can end up pointing at nothing: a month the
 * PM picked before the records behind it changed. Falling back to All Months
 * shows the whole report rather than an empty screen with a stale month in the
 * box.
 */
export function resolveReportMonth(
  selected: string | null | undefined,
  months: readonly string[] | null | undefined,
): string {
  const month = reportMonthParam(selected);
  if (!month) return REPORT_MONTH_ALL;
  return (months ?? []).includes(month) ? month : REPORT_MONTH_ALL;
}

// ---------------------------------------------------------------------------
// Copy
// ---------------------------------------------------------------------------

export const REPORT_TITLE = "Production Status";
export const REPORT_ALL_PROJECTS = "Cumulative report - all projects";

export const REPORT_EMPTY_TITLE = "No production status records available.";
export const REPORT_EMPTY_HINT =
  "Once a Project Head or an activity Lead records an update, it appears here as that revision and activity's current status.";

// A selected month with nothing in it. Deliberately its own wording: telling a
// PM who picked the wrong month that production status has never been recorded
// would be plainly false. Neither state is an error.
export const REPORT_EMPTY_MONTH_TITLE =
  "No production status records for this month.";
export const REPORT_EMPTY_MONTH_HINT =
  "Nothing was recorded in the month selected. Choose another month, or All Months for the full cumulative report.";

export const REPORT_ERROR_TITLE = "Couldn't load the production status report";
export const REPORT_DOWNLOAD_ERROR =
  "Couldn't download the report. Please try again.";
export const REPORT_NOTHING_TO_DOWNLOAD =
  "There is nothing to download yet.";

/**
 * Turn a failed request into something a user can act on. Mirrors
 * `production-status.ts::productionStatusErrorMessage`, with the 403 reworded
 * for the one rule this endpoint adds.
 */
export function reportErrorMessage(
  status: number | null,
  message: string | null,
): string {
  if (status === 403) {
    return (
      message ??
      "Only the project manager can view the cumulative production status report."
    );
  }
  if (status === 0) {
    return "Could not reach the server. Check your connection and try again.";
  }
  return message ?? "Something went wrong. Please try again.";
}
