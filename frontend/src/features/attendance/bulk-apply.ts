/**
 * Bulk attendance (Phase 3 UI) - everything the page decides, kept pure.
 *
 * No React and no `@/` alias for values, so the host-Node harness loads this
 * file directly; the component only renders what these functions return.
 *
 * THE CONTRACT (`POST /attendance/bulk-apply`, `attendance/bulk_apply.py`)
 * ======================================================================
 * One status over employees x dates. `dry_run: true` previews and writes
 * nothing; `dry_run: false` applies with partial success. Every pair comes back
 * with exactly one outcome - created / updated / unchanged / protected /
 * rejected - and the server re-judges every pair on apply, so a preview is a
 * forecast, never a promise. STATUS ONLY: the body has no check-in/check-out
 * field at all, so a future day can never be sent times.
 *
 * WHAT STAYS ON THE SERVER
 * ========================
 * Working-day rules, the past-date reason rule, leave protection, permissions
 * and the size limits are all enforced there. The copies here exist only so the
 * PM is told before a request is refused - the server's verdict is what the
 * preview and results show.
 */
import { isFutureDate, isPastDate, REASON_REQUIRED_MESSAGE } from "./date-rules.ts";
import { isWeekend } from "./month.ts";
import { ATTENDANCE_STATUSES, ATTENDANCE_STATUS_LABEL } from "./schemas.ts";
import type {
  AttendanceBulkApplyBody,
  AttendanceBulkApplyItem,
  AttendanceBulkApplyOutcome,
  AttendanceBulkApplyResult,
  AttendanceStatus,
} from "./types";

// ---------------------------------------------------------------------------
// Limits - `attendance/schemas.py` MAX_BULK_*. Exceeding one is refused here
// with an explanation; a selection is never silently truncated.
// ---------------------------------------------------------------------------
export const MAX_BULK_EMPLOYEES = 200;
export const MAX_BULK_DATES = 62;
export const MAX_BULK_PAIRS = 500;
export const MAX_NOTE_LEN = 500;
/** A range longer than this is not expanded into a date list at all. */
export const MAX_RANGE_DAYS = 366;

export type BulkMode = "one-employee" | "one-date";

export const OUTCOMES: readonly AttendanceBulkApplyOutcome[] = [
  "created",
  "updated",
  "unchanged",
  "protected",
  "rejected",
];

// ---------------------------------------------------------------------------
// Dates
// ---------------------------------------------------------------------------
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

function parseIso(iso: string): { y: number; m: number; d: number } | null {
  if (!ISO_DATE.test(iso)) return null;
  const [y, m, d] = iso.split("-").map(Number);
  const probe = new Date(Date.UTC(y, m - 1, d));
  // Rejects 2026-02-30 and friends, which Date would roll into March.
  if (probe.getUTCFullYear() !== y || probe.getUTCMonth() !== m - 1 || probe.getUTCDate() !== d) {
    return null;
  }
  return { y, m: m - 1, d };
}

export function isIsoDate(iso: string): boolean {
  return parseIso(iso) !== null;
}

/**
 * Every date from `from` to `to`, inclusive, as ISO strings.
 * `null` when either end is invalid, the range runs backwards, or it is longer
 * than MAX_RANGE_DAYS (the caller explains which).
 */
export function datesInRange(from: string, to: string): string[] | null {
  const a = parseIso(from);
  const b = parseIso(to);
  if (!a || !b || from > to) return null;
  const out: string[] = [];
  // UTC arithmetic: a calendar day is never 23 or 25 hours long here.
  const cursor = new Date(Date.UTC(a.y, a.m, a.d));
  const end = Date.UTC(b.y, b.m, b.d);
  while (cursor.getTime() <= end) {
    if (out.length >= MAX_RANGE_DAYS) return null;
    out.push(cursor.toISOString().slice(0, 10));
    cursor.setUTCDate(cursor.getUTCDate() + 1);
  }
  return out;
}

/** `"2026-10-13"` -> `"Tue, 13 Oct 2026"`. Rendered in UTC so the browser's own
 *  zone can never shift the calendar day being described. */
export function formatBulkDate(iso: string): string {
  const p = parseIso(iso);
  if (!p) return iso;
  return new Date(Date.UTC(p.y, p.m, p.d)).toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** The company calendar for the range, as `day-status.calendarDayMaps` builds it. */
export interface CalendarOverrides {
  off: ReadonlyMap<string, string>;
  working: ReadonlyMap<string, string>;
}

const ORDINAL = ["1st", "2nd", "3rd", "4th", "5th"];

/**
 * Why a date is NOT a working day, or `null` when it is one.
 *
 * Mirrors `calendar/working_days.py::is_working_day`, in its order: a declared
 * working day wins; an office-closing entry closes the day; otherwise the office
 * week (Sunday, 2nd/4th Saturday - NOT every Saturday). Display only - the
 * server re-decides every date and rejects a non-working one it is not told to
 * include, whatever this says.
 */
export function nonWorkingReason(iso: string, calendar: CalendarOverrides): string | null {
  const p = parseIso(iso);
  if (!p) return null;
  if (calendar.working.has(iso)) return null;
  const closed = calendar.off.get(iso);
  if (closed !== undefined) return closed ? `Holiday - ${closed}` : "Holiday";
  if (!isWeekend(p.y, p.m, p.d)) return null;
  const dow = new Date(Date.UTC(p.y, p.m, p.d)).getUTCDay();
  if (dow === 0) return "Sunday";
  return `${ORDINAL[Math.floor((p.d - 1) / 7)]} Saturday`;
}

/** One date of a Mode A range and what happens to it. */
export interface PlannedDate {
  date: string;
  /** Why the office is closed, or null on a working day. */
  nonWorking: string | null;
  /** The PM unticked it. */
  excludedByPm: boolean;
  /** Sent in the request. */
  included: boolean;
  /** Why it is NOT sent - shown beside the date so nothing vanishes silently. */
  skipNote: string | null;
}

/**
 * Mode A: a date range as the dates the request will carry.
 *
 * Non-working days are left out by default and listed with the reason; ticking
 * "include non-working days" puts them back (and sends `include_non_working`).
 * A date the PM unticked is listed as excluded, never dropped from view.
 */
export function planRangeDates(input: {
  dates: readonly string[];
  excluded: ReadonlySet<string>;
  includeNonWorking: boolean;
  calendar: CalendarOverrides;
}): PlannedDate[] {
  return input.dates.map((date) => {
    const nonWorking = nonWorkingReason(date, input.calendar);
    const excludedByPm = input.excluded.has(date);
    const skippedAsOff = nonWorking !== null && !input.includeNonWorking;
    let skipNote: string | null = null;
    if (excludedByPm) skipNote = "Excluded by you";
    else if (skippedAsOff) skipNote = `Skipped - non-working day (${nonWorking})`;
    return {
      date,
      nonWorking,
      excludedByPm,
      included: !excludedByPm && !skippedAsOff,
      skipNote,
    };
  });
}

// ---------------------------------------------------------------------------
// The draft and its validation
// ---------------------------------------------------------------------------
export interface BulkDraft {
  mode: BulkMode;
  employeeIds: readonly string[];
  /** The dates the request will carry (Mode A: the included ones only). */
  dates: readonly string[];
  status: AttendanceStatus | "";
  /** The action's one reason. Never pre-filled from an existing record. */
  note: string;
  includeNonWorking: boolean;
}

export function isAttendanceStatus(value: unknown): value is AttendanceStatus {
  return typeof value === "string" && (ATTENDANCE_STATUSES as readonly string[]).includes(value);
}

/** Size-limit problems for a selection, each with what to do about it. */
export function checkLimits(employeeCount: number, dateCount: number): string[] {
  const problems: string[] = [];
  if (employeeCount > MAX_BULK_EMPLOYEES) {
    problems.push(
      `${employeeCount} employees are selected; one bulk update can cover at most ${MAX_BULK_EMPLOYEES}. Deselect some and run the rest as a separate update.`,
    );
  }
  if (dateCount > MAX_BULK_DATES) {
    problems.push(
      `${dateCount} dates are included; one bulk update can cover at most ${MAX_BULK_DATES}. Shorten the range or exclude dates, and run the rest as a separate update.`,
    );
  }
  const pairs = employeeCount * dateCount;
  if (pairs > MAX_BULK_PAIRS) {
    problems.push(
      `This covers ${pairs} employee-days; one bulk update can cover at most ${MAX_BULK_PAIRS}. Reduce the employees or dates.`,
    );
  }
  return problems;
}

/** The past dates in a draft - the ones the reason rule applies to. */
export function pastDates(dates: readonly string[], today: string): string[] {
  return dates.filter((d) => isPastDate(d, today));
}

export function futureDates(dates: readonly string[], today: string): string[] {
  return dates.filter((d) => isFutureDate(d, today));
}

/**
 * Everything that stops a preview, as actionable messages. Empty = ready.
 *
 * The reason rule is the server's (`_assert_reason_for_past` /
 * `reason_required`): a past day that would CHANGE needs one. Which past days
 * would change is only known after a preview, so a reason is asked for whenever
 * any past date is included - the same stance the single-record dialog takes.
 */
export function validateDraft(draft: BulkDraft, today: string): string[] {
  const errors: string[] = [];
  if (draft.employeeIds.length === 0) {
    errors.push(
      draft.mode === "one-employee"
        ? "Select an employee."
        : "Select at least one employee.",
    );
  }
  if (draft.dates.length === 0) {
    errors.push(
      draft.mode === "one-employee"
        ? "No dates are included. Pick a date range, or include dates that are currently skipped or excluded."
        : "Select an attendance date.",
    );
  }
  if (draft.dates.some((d) => !isIsoDate(d))) {
    errors.push("One of the dates is not a valid calendar date.");
  }
  if (!isAttendanceStatus(draft.status)) {
    errors.push("Choose the attendance status to apply.");
  }
  errors.push(...checkLimits(new Set(draft.employeeIds).size, new Set(draft.dates).size));
  if (draft.note.length > MAX_NOTE_LEN) {
    errors.push(`Keep the reason under ${MAX_NOTE_LEN} characters.`);
  }
  const past = pastDates(draft.dates, today);
  if (past.length > 0 && draft.note.trim() === "") {
    errors.push(
      past.length === draft.dates.length
        ? REASON_REQUIRED_MESSAGE
        : `${REASON_REQUIRED_MESSAGE} ${past.length} of the ${draft.dates.length} dates are in the past.`,
    );
  }
  return errors;
}

/** Whether the reason box must be filled for this draft. */
export function reasonRequired(dates: readonly string[], today: string): boolean {
  return pastDates(dates, today).length > 0;
}

// ---------------------------------------------------------------------------
// Request bodies
// ---------------------------------------------------------------------------
/**
 * The PREVIEW body for a validated draft. `dry_run` is pinned to true here and
 * nowhere else, so the preview step cannot write.
 *
 * Employees keep the order they were picked in (the server answers in request
 * order); duplicates are dropped. Dates are sorted.
 */
export function previewBody(draft: BulkDraft): AttendanceBulkApplyBody {
  if (!isAttendanceStatus(draft.status)) {
    throw new Error("previewBody: draft has no valid status");
  }
  const note = draft.note.trim();
  return {
    employee_ids: Array.from(new Set(draft.employeeIds)),
    dates: Array.from(new Set(draft.dates)).sort(),
    status: draft.status,
    note: note === "" ? null : note,
    include_non_working: draft.includeNonWorking,
    dry_run: true,
  };
}

/**
 * The APPLY body for a preview that was shown: the very same request with only
 * `dry_run` flipped. What the PM confirms is exactly what was previewed - the
 * draft is never rebuilt between the two steps.
 */
export function applyBodyFor(previewed: AttendanceBulkApplyBody): AttendanceBulkApplyBody {
  return { ...previewed, dry_run: false };
}

// ---------------------------------------------------------------------------
// Response verification
// ---------------------------------------------------------------------------
export type Verified =
  | { ok: true; result: AttendanceBulkApplyResult }
  | { ok: false; problem: string };

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === "object" && v !== null && !Array.isArray(v);
}

/**
 * Accept a response only if it answers THIS request completely.
 *
 * The server returns exactly one item per employee x date pair. Anything less,
 * more, or different - a missing pair, an unknown outcome, a preview where an
 * apply was asked for - is refused, so no row is ever shown with an outcome the
 * server did not give it. Totals are re-derived from the rows and must agree
 * with the server's own summary.
 */
export function verifyBulkResult(raw: unknown, request: AttendanceBulkApplyBody): Verified {
  if (!isObject(raw)) return { ok: false, problem: "The response was empty or not an object." };
  if (raw.dry_run !== request.dry_run) {
    return {
      ok: false,
      problem: request.dry_run
        ? "The server did not answer as a preview."
        : "The server answered as a preview, not as a save.",
    };
  }
  if (raw.status !== request.status) {
    return { ok: false, problem: "The response is for a different status." };
  }
  if (!request.dry_run && (typeof raw.bulk_action_id !== "string" || raw.bulk_action_id === "")) {
    return { ok: false, problem: "The save response carries no action id." };
  }
  if (!Array.isArray(raw.results)) {
    return { ok: false, problem: "The response has no per-row results." };
  }

  const employees = new Set(request.employee_ids);
  const dates = new Set(request.dates);
  const expected = employees.size * dates.size;
  if (raw.results.length !== expected) {
    return {
      ok: false,
      problem: `Expected ${expected} row results, received ${raw.results.length}.`,
    };
  }

  const seen = new Set<string>();
  for (const item of raw.results as unknown[]) {
    if (!isObject(item)) return { ok: false, problem: "A row result is not an object." };
    const { employee_id, attendance_date, outcome, warnings } = item;
    if (typeof employee_id !== "string" || !employees.has(employee_id)) {
      return { ok: false, problem: "A row result names an employee that was not requested." };
    }
    if (typeof attendance_date !== "string" || !dates.has(attendance_date)) {
      return { ok: false, problem: "A row result names a date that was not requested." };
    }
    if (!(OUTCOMES as readonly unknown[]).includes(outcome)) {
      return { ok: false, problem: "A row result has an unknown outcome." };
    }
    if (warnings !== undefined && !Array.isArray(warnings)) {
      return { ok: false, problem: "A row result has malformed warnings." };
    }
    const key = `${employee_id}|${attendance_date}`;
    if (seen.has(key)) {
      return { ok: false, problem: "The same employee-date appears twice in the response." };
    }
    seen.add(key);
  }

  const result = raw as unknown as AttendanceBulkApplyResult;
  const tally = tallyResults(result.results);
  const summary = raw.summary;
  if (!isObject(summary) || OUTCOMES.some((o) => summary[o] !== tally[o])) {
    return { ok: false, problem: "The response summary does not match its rows." };
  }
  return { ok: true, result };
}

// ---------------------------------------------------------------------------
// Reading results
// ---------------------------------------------------------------------------
export interface Tally {
  total: number;
  created: number;
  updated: number;
  unchanged: number;
  protected: number;
  rejected: number;
  /** created + updated: rows that (would) actually change. */
  changed: number;
  /** protected + rejected: rows that were (or would be) refused. */
  refused: number;
}

/** Totals counted from the rows themselves - never from anything assumed. */
export function tallyResults(rows: readonly Pick<AttendanceBulkApplyItem, "outcome">[]): Tally {
  const t: Tally = {
    total: rows.length,
    created: 0,
    updated: 0,
    unchanged: 0,
    protected: 0,
    rejected: 0,
    changed: 0,
    refused: 0,
  };
  for (const r of rows) {
    if ((OUTCOMES as readonly string[]).includes(r.outcome)) t[r.outcome] += 1;
  }
  t.changed = t.created + t.updated;
  t.refused = t.protected + t.rejected;
  return t;
}

/** What each outcome reads as, before and after the save. */
export const OUTCOME_LABEL: Record<
  "preview" | "applied",
  Record<AttendanceBulkApplyOutcome, string>
> = {
  preview: {
    created: "Will create",
    updated: "Will update",
    unchanged: "Already set",
    protected: "Protected - leave",
    rejected: "Rejected",
  },
  applied: {
    created: "Created",
    updated: "Updated",
    unchanged: "No change needed",
    protected: "Not changed - leave",
    rejected: "Not saved",
  },
};

export const OUTCOME_VARIANT: Record<
  AttendanceBulkApplyOutcome,
  "success" | "neutral" | "warning" | "danger"
> = {
  created: "success",
  updated: "success",
  unchanged: "neutral",
  protected: "warning",
  rejected: "danger",
};

/** The server's warning for a day a pending leave request covers. */
export const PENDING_LEAVE_WARNING = "pending_leave_request";

/** Rows the server flagged because a pending leave request covers the day. */
export function leaveBlockingRows(
  rows: readonly AttendanceBulkApplyItem[],
): AttendanceBulkApplyItem[] {
  return rows.filter((r) => (r.warnings ?? []).some((w) => w.code === PENDING_LEAVE_WARNING));
}

const WORKED: readonly AttendanceStatus[] = ["present", "half_day"];

/**
 * The general consequence of planning a worked day ahead.
 *
 * The server's established rule (`leave.service._WORKED_ATTENDANCE`): a Present
 * or Half day record blocks a leave request for that day - it cannot be
 * requested, edited onto, or approved while the record stands. The server only
 * warns per row when a PENDING request already exists; this note covers the
 * requests that do not exist yet. It never changes the chosen status.
 */
export function futureWorkedNotice(
  status: AttendanceStatus | "",
  dates: readonly string[],
  today: string,
): string | null {
  if (!isAttendanceStatus(status) || !WORKED.includes(status)) return null;
  const future = futureDates(dates, today);
  if (future.length === 0) return null;
  const label = ATTENDANCE_STATUS_LABEL[status];
  const span = future.length === 1 ? "that future day" : `those ${future.length} future days`;
  return `Marking ${span} ${label} blocks leave for ${future.length === 1 ? "it" : "them"}: the employee cannot request leave there, and a pending request cannot be approved, until the day is changed.`;
}

export type ApplyVerdict = "all_saved" | "partial" | "nothing_saved" | "nothing_to_change";

/**
 * The one-line verdict on an APPLIED result. Partial success is never reported
 * as success: one refused row makes the whole action "partial".
 */
export function applyVerdict(t: Tally): ApplyVerdict {
  if (t.changed === 0) return t.refused > 0 ? "nothing_saved" : "nothing_to_change";
  return t.refused > 0 ? "partial" : "all_saved";
}

export const VERDICT_TEXT: Record<ApplyVerdict, string> = {
  all_saved: "All changes were saved.",
  partial: "Partially applied - some rows were not saved.",
  nothing_saved: "Nothing was saved - every row was refused.",
  nothing_to_change: "Nothing to change - every row already had this status.",
};

/** How many pairs came out of the save differently from the preview. */
export function changedSincePreview(
  preview: readonly AttendanceBulkApplyItem[],
  applied: readonly AttendanceBulkApplyItem[],
): number {
  const before = new Map(preview.map((r) => [`${r.employee_id}|${r.attendance_date}`, r.outcome]));
  let n = 0;
  for (const r of applied) {
    if (before.get(`${r.employee_id}|${r.attendance_date}`) !== r.outcome) n += 1;
  }
  return n;
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------
/** The parts of `lib/api-client.AppError` read here (structural, so tests need
 *  no import of the client). */
interface ErrorLike {
  code?: unknown;
  status?: unknown;
  message?: unknown;
  details?: unknown;
}

export interface BulkErrorView {
  message: string;
  /**
   * True when the save may or may not have happened (connection lost, timeout,
   * server error). The page must then NOT offer a resubmit - the PM checks the
   * days first.
   */
  ambiguous: boolean;
}

/** The first pydantic message of a 422 envelope, e.g. the pair-limit refusal. */
function firstValidationMessage(details: unknown): string | null {
  if (!isObject(details) || !Array.isArray(details.errors)) return null;
  const first = details.errors[0];
  if (!isObject(first) || typeof first.msg !== "string") return null;
  return first.msg.replace(/^Value error,\s*/, "");
}

/**
 * A failed request as something safe to show. Messages come only from the
 * backend's error envelope (written for users) or from fixed text here - never
 * a stack, a raw body, or an internal error string.
 */
export function describeBulkError(err: unknown, phase: "preview" | "apply"): BulkErrorView {
  const e = (isObject(err) ? err : {}) as ErrorLike;
  const status = typeof e.status === "number" ? e.status : 0;
  const code = typeof e.code === "string" ? e.code : "";
  const serverMessage = typeof e.message === "string" ? e.message : "";

  const lostTouch =
    status === 0 || code === "network_error" || code === "parse_error" || status === 408 || status >= 500;
  if (lostTouch) {
    if (phase === "preview") {
      return {
        message: "The preview could not be completed. Nothing was saved - run the preview again.",
        ambiguous: false,
      };
    }
    return {
      message:
        "The save did not get a clear answer from the server. Some or all records may already have been saved. It was not retried - check the days on the Records tab before running it again.",
      ambiguous: true,
    };
  }
  if (status === 401 || status === 403) {
    return { message: "You don't have permission to change attendance.", ambiguous: false };
  }
  if (status === 422) {
    const detail = firstValidationMessage(e.details);
    return {
      message: detail ? `The server refused the request: ${detail}` : "The server refused the request as invalid.",
      ambiguous: false,
    };
  }
  return {
    message: serverMessage ? `The server refused the request: ${serverMessage}` : "The request was refused.",
    ambiguous: false,
  };
}

// ---------------------------------------------------------------------------
// Running the two requests
// ---------------------------------------------------------------------------
export type Send = (body: AttendanceBulkApplyBody) => Promise<unknown>;

export type RunOutcome =
  | { kind: "result"; request: AttendanceBulkApplyBody; result: AttendanceBulkApplyResult }
  | { kind: "unverified"; request: AttendanceBulkApplyBody; problem: string }
  | { kind: "error"; request: AttendanceBulkApplyBody; error: BulkErrorView };

/** Send a PREVIEW. Refuses outright to send a body that is not a dry run. */
export async function runPreview(send: Send, body: AttendanceBulkApplyBody): Promise<RunOutcome> {
  if (body.dry_run !== true) throw new Error("runPreview: refusing to send a non-dry-run body");
  try {
    const verified = verifyBulkResult(await send(body), body);
    return verified.ok
      ? { kind: "result", request: body, result: verified.result }
      : { kind: "unverified", request: body, problem: verified.problem };
  } catch (err) {
    return { kind: "error", request: body, error: describeBulkError(err, "preview") };
  }
}

/**
 * A one-shot APPLY for one confirmed preview.
 *
 * The returned function sends at most ONCE in its lifetime: a second call -
 * a double click, a re-render, a retry after a timeout - resolves to `null`
 * without touching the network. A failed or ambiguous save is never retried;
 * trying again means a fresh preview and a fresh confirmation. (The server is
 * still the real guard: a repeated apply finds every row already set and
 * reports `unchanged`.)
 */
export function createApplyOnce(send: Send): (previewed: AttendanceBulkApplyBody) => Promise<RunOutcome | null> {
  let used = false;
  return async (previewed) => {
    if (used) return null;
    used = true;
    const body = applyBodyFor(previewed);
    try {
      const verified = verifyBulkResult(await send(body), body);
      return verified.ok
        ? { kind: "result", request: body, result: verified.result }
        : { kind: "unverified", request: body, problem: verified.problem };
    } catch (err) {
      return { kind: "error", request: body, error: describeBulkError(err, "apply") };
    }
  };
}
