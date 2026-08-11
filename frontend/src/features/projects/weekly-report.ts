/**
 * Project Weekly Report presentation logic (Phase 7).
 *
 * Same split as summary.ts: every rule the tab follows - which cycle is
 * selected, how the date range reads, and the exact string in every cell - is
 * decided here, and the component only renders the result. The repo's
 * `node --test` harness has no jsdom or React Testing Library, so logic inside
 * JSX cannot be covered at all.
 *
 * This module does NO report arithmetic. Rows arrive finished from the backend
 * (`projects/weekly_report.py`), which is the same dataset the Excel download
 * renders. Deriving anything here - a benchmark, a count, a task status - would
 * create a second definition that could disagree with the file the Head just
 * downloaded, which is the one thing this feature must never do.
 *
 * Deliberately dependency-free (like scope.ts, summary.ts and tabs.ts) so
 * `node --test` can cover it without a bundler.
 */

/** The two selectable cycles. No arbitrary date range in this phase. */
export type WeeklyReportCycle = "current" | "previous";

export const WEEKLY_REPORT_CYCLES: readonly {
  value: WeeklyReportCycle;
  label: string;
}[] = [
  // Previous first, so the control reads left-to-right in time order.
  { value: "previous", label: "Previous Week" },
  { value: "current", label: "Current Week" },
];

/** What the tab opens on. */
export const WEEKLY_REPORT_DEFAULT_CYCLE: WeeklyReportCycle = "current";

/** Query-string key backing the selected cycle (`?tab=weekly-report&cycle=previous`). */
export const WEEKLY_REPORT_CYCLE_PARAM = "cycle";

/**
 * Normalise whatever is in the URL into a cycle the API will accept. Anything
 * unrecognised falls back to Current Week rather than firing a request that
 * comes back 422.
 */
export function resolveWeeklyReportCycle(raw: unknown): WeeklyReportCycle {
  return WEEKLY_REPORT_CYCLES.some((c) => c.value === raw)
    ? (raw as WeeklyReportCycle)
    : WEEKLY_REPORT_DEFAULT_CYCLE;
}

/**
 * The two request paths, built from the SAME project and cycle.
 *
 * They live here, next to each other and unit-tested, because the whole feature
 * rests on one promise: the file the Head downloads is the week they are
 * looking at. A download that quietly sent `cycle=current` while "Previous
 * Week" was on screen would break that promise silently - nothing would error,
 * the file would simply describe the wrong week.
 */
export function weeklyReportPath(projectId: string, cycle: WeeklyReportCycle): string {
  return `/projects/${projectId}/weekly-report?cycle=${cycle}`;
}

export function weeklyReportExportPath(
  projectId: string,
  cycle: WeeklyReportCycle,
): string {
  return `/projects/${projectId}/weekly-report.xlsx?cycle=${cycle}`;
}

/** One report row exactly as the API returns it. */
export interface WeeklyReportApiRow {
  report_date: string;
  work_period: string;
  work_period_label: string;
  employee_name: string;
  project_code: string;
  activity_name?: string | null;
  sub_activity_name?: string | null;
  benchmark?: number | null;
  benchmark_label?: string | null;
  tags?: number | null;
  docs?: number | null;
  bom?: number | null;
  spares?: number | null;
  pages?: number | null;
  records?: number | null;
  task_status?: string | null;
  task_status_label?: string | null;
  remarks?: string | null;
}

export interface WeeklyReportPayload {
  project_code?: string | null;
  period?: { type?: string | null; start_date?: string | null; end_date?: string | null } | null;
  rows?: WeeklyReportApiRow[] | null;
  row_count?: number | null;
}

/**
 * Stands in for a value that does not apply to this row.
 *
 * A plain hyphen, matching summary.ts, the company's own Head Report workbook
 * and the generated .xlsx. Never a 0: "no docs apply to this activity" and "0
 * docs were counted against the target" are different statements, and printing
 * a zero for the first would invent work that was never measured.
 */
export const VALUE_NOT_APPLICABLE = "-";

export const WEEKLY_REPORT_EMPTY_TITLE = "No work reported this week";
export const WEEKLY_REPORT_EMPTY_HINT =
  "No work reports were recorded for this project during this week.";
export const WEEKLY_REPORT_ERROR_TITLE = "Unable to load the weekly report.";
export const WEEKLY_REPORT_ERROR_HINT = "Please try again.";
export const WEEKLY_REPORT_FORBIDDEN_TITLE = "Weekly Report is not available";
export const WEEKLY_REPORT_FORBIDDEN_HINT =
  "Only this project's assigned Head can open the Weekly Report.";
export const WEEKLY_REPORT_DOWNLOAD_ERROR =
  "Unable to generate the weekly report Excel file.";

/** Table columns, in the same order as the Excel sheet (which adds SL.NO). */
export const WEEKLY_REPORT_COLUMNS: readonly {
  key: string;
  label: string;
  /** Numeric columns are centred and never wrap. */
  numeric?: boolean;
  /** Free text that can outrun its column and must wrap instead of clipping. */
  wrap?: boolean;
}[] = [
  { key: "date", label: "Date" },
  { key: "workPeriod", label: "Work Period" },
  { key: "employee", label: "Employee" },
  { key: "project", label: "Project" },
  { key: "activity", label: "Activity", wrap: true },
  { key: "subActivity", label: "Sub-Activity", wrap: true },
  { key: "benchmark", label: "Benchmark", numeric: true },
  { key: "tags", label: "Tags", numeric: true },
  { key: "docs", label: "Docs", numeric: true },
  { key: "bom", label: "BOM", numeric: true },
  { key: "spares", label: "Spares", numeric: true },
  { key: "pages", label: "Pages", numeric: true },
  { key: "records", label: "Records", numeric: true },
  { key: "taskStatus", label: "Task Status" },
  { key: "remarks", label: "Remarks", wrap: true },
];

/** Format a count, or the placeholder when the unit does not apply. */
export function formatCountCell(value: unknown): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return VALUE_NOT_APPLICABLE;
  return value.toLocaleString("en-US");
}

/**
 * The Benchmark cell: the numeric target when there is one, else the textual
 * label a completion-only task carries ("Lump Sum"), else the placeholder.
 *
 * Exactly the rule the workbook applies, because both read the same two API
 * fields. Nothing is derived from the activity's name.
 */
export function formatBenchmarkCell(row: WeeklyReportApiRow): string {
  if (typeof row.benchmark === "number" && Number.isFinite(row.benchmark)) {
    // Trim a trailing .00 - a target of 150 should not read "150.00".
    return Number(row.benchmark.toFixed(2)).toLocaleString("en-US");
  }
  return row.benchmark_label?.trim() || VALUE_NOT_APPLICABLE;
}

/**
 * "07 Aug 2026" from an ISO date, without going through the browser's timezone.
 *
 * `new Date("2026-08-07")` parses as UTC midnight and renders as the 6th in any
 * timezone behind UTC, which would silently shift every date in the report by a
 * day. The parts are formatted from the string itself instead.
 */
const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export function formatReportDate(iso: unknown): string {
  if (typeof iso !== "string") return VALUE_NOT_APPLICABLE;
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return VALUE_NOT_APPLICABLE;
  const [, year, month, day] = match;
  const name = MONTHS[Number(month) - 1];
  if (!name) return VALUE_NOT_APPLICABLE;
  return `${day} ${name} ${year}`;
}

/**
 * "07 Aug 2026 - 13 Aug 2026" - the resolved cycle, always shown so the Head
 * never has to guess what "Current Week" meant.
 */
export function formatCycleRange(
  start: unknown,
  end: unknown,
): string {
  const from = formatReportDate(start);
  const to = formatReportDate(end);
  if (from === VALUE_NOT_APPLICABLE || to === VALUE_NOT_APPLICABLE) {
    return VALUE_NOT_APPLICABLE;
  }
  return `${from} - ${to}`;
}

/** One fully formatted table row. Every cell is a non-empty string. */
export interface WeeklyReportTableRow {
  key: string;
  date: string;
  workPeriod: string;
  employee: string;
  /** PROJECT CODE ONLY - never the project name. */
  project: string;
  activity: string;
  subActivity: string;
  benchmark: string;
  tags: string;
  docs: string;
  bom: string;
  spares: string;
  pages: string;
  records: string;
  taskStatus: string;
  remarks: string;
}

/**
 * Format the API rows for the table, preserving their order exactly.
 *
 * The server already sorted them (date, work period, employee, activity) and
 * the workbook renders that same order, so re-sorting here would be the one way
 * the screen and the file could end up disagreeing.
 */
export function buildWeeklyReportRows(
  rows: readonly WeeklyReportApiRow[] | null | undefined,
): WeeklyReportTableRow[] {
  return (rows ?? []).map((r, index) => ({
    // Index-based key: rows carry no id, and two genuinely identical lines on
    // one day would otherwise collide. Order is stable per fetch, so this is a
    // safe React key.
    key: `${r.report_date}-${r.work_period}-${r.employee_name}-${index}`,
    date: formatReportDate(r.report_date),
    workPeriod: r.work_period_label?.trim() || VALUE_NOT_APPLICABLE,
    employee: r.employee_name?.trim() || VALUE_NOT_APPLICABLE,
    project: r.project_code?.trim() || VALUE_NOT_APPLICABLE,
    activity: r.activity_name?.trim() || VALUE_NOT_APPLICABLE,
    subActivity: r.sub_activity_name?.trim() || VALUE_NOT_APPLICABLE,
    benchmark: formatBenchmarkCell(r),
    tags: formatCountCell(r.tags),
    docs: formatCountCell(r.docs),
    bom: formatCountCell(r.bom),
    spares: formatCountCell(r.spares),
    pages: formatCountCell(r.pages),
    records: formatCountCell(r.records),
    taskStatus: r.task_status_label?.trim() || VALUE_NOT_APPLICABLE,
    remarks: r.remarks?.trim() || VALUE_NOT_APPLICABLE,
  }));
}

/**
 * Whether the Download button may be pressed.
 *
 * Disabled while the week is still loading and while it holds nothing: the
 * backend would happily return a valid header-only workbook, but handing the
 * Head an empty file is a worse answer than a disabled button next to "No work
 * reported this week".
 */
export function canDownloadWeeklyReport(
  rows: readonly unknown[] | null | undefined,
  isLoading: boolean,
): boolean {
  return !isLoading && (rows?.length ?? 0) > 0;
}
