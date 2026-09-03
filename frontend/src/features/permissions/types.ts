/**
 * Permission = 1h or 2h of sanctioned absence inside an otherwise normal working
 * day, drawn from a 4h monthly allowance. Nothing to do with RBAC capabilities
 * (see `lib/rbac.ts` for those).
 *
 * The pure helpers at the bottom are import-free on purpose so the host-Node unit
 * test can load this file directly - the repo has no DOM test harness, so the way
 * a rule is made testable is to keep it out of the component.
 */
export type PermissionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "cancelled"
  /** Approved permission the employee has asked to withdraw (Phase 4E). The
   *  permission still STANDS and its hours are still spent until an authorised
   *  reviewer decides - the same state, with the same meaning, as
   *  `LeaveStatus.cancellation_requested`. */
  | "cancellation_requested";

/** The only legal durations. No 30 minutes, no custom value, no decimals. */
export const PERMISSION_DURATIONS = [1, 2] as const;

export type PermissionDuration = (typeof PERMISSION_DURATIONS)[number];

/**
 * The four selectable permission options (Phase 4C) - the ONE authoritative
 * value a requester picks. There is no plain "1 Hour" / "2 Hours" choice any
 * more: every request names a half, so a reviewer never has to infer one from
 * `duration_hours` alone.
 */
export const PERMISSION_PERIOD_OPTIONS = [
  "first_half_1h",
  "second_half_1h",
  "first_half_2h",
  "second_half_2h",
] as const;

export type PermissionPeriod = (typeof PERMISSION_PERIOD_OPTIONS)[number];

/** The exact wording the form, the detail page and the email all show.
 *
 *  A PLAIN ASCII hyphen, never an em or en dash - this used to be an em dash and
 *  the product corrected it. It is a house rule across CoreOps, not a preference
 *  local to permissions. Must stay character-for-character identical to
 *  `permissions/models.py::PERIOD_LABELS`, which is what the emails and
 *  notifications render from. */
export const PERMISSION_PERIOD_LABEL: Record<PermissionPeriod, string> = {
  first_half_1h: "1st Half - 1 Hour",
  second_half_1h: "2nd Half - 1 Hour",
  first_half_2h: "1st Half - 2 Hours",
  second_half_2h: "2nd Half - 2 Hours",
};

/** How many hours each option costs - what the live balance preview and the
 *  affordability check (`isDurationAffordable`) run against. */
export const PERMISSION_PERIOD_HOURS: Record<PermissionPeriod, PermissionDuration> = {
  first_half_1h: 1,
  second_half_1h: 1,
  first_half_2h: 2,
  second_half_2h: 2,
};

/** The company allowance, mirrored from `permissions/balance.py` for the preview
 *  only. Every decision is made against the server's figure. */
export const MONTHLY_ALLOWANCE_HOURS = 4;

export interface PermissionRequest {
  id: string;
  employee_id: string;
  /** Resolved by the BACKEND on every list row and on the detail (Phase 4E).
   *  Never resolve this in the browser from `GET /employees`: that endpoint is
   *  RBAC-scoped and returns only their own row to a plain employee-role actor -
   *  which a Project Head still is - so a reviewer's queue had nothing to look a
   *  colleague up in and printed a UUID prefix instead. Null only on the
   *  responses a mutation returns, which carry no name and need none. */
  employee_name: string | null;
  permission_date: string;
  duration_hours: number;
  /** NULL only for a request filed before Phase 4C, which recorded no half. */
  period: PermissionPeriod | null;
  reason: string | null;
  status: PermissionStatus;
  manager_id: string | null;
  manager_comment: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PermissionRequestPage {
  items: PermissionRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface PermissionRequestCreateBody {
  permission_date: string;
  period: PermissionPeriod;
  reason?: string | null;
}

export interface PermissionReviewBody {
  comment?: string | null;
}

/** One employee's permission standing for one calendar month. Derived
 *  server-side; `remaining_hours` is authoritative and the preview below is
 *  only a convenience. */
export interface PermissionBalance {
  employee_id: string;
  month: string; // first day of the month
  allowance_hours: number;
  approved_hours: number;
  remaining_hours: number;
  /** Whether this is the month running now, on the Chennai business calendar. */
  is_current_month: boolean;
  /** Whether a NEW request may be filed against this month. False once the month
   *  has ended: the allowance does not carry forward, so there is nothing left
   *  to spend. The figures stay true and readable either way - a closed month is
   *  history, not a hidden month. The refusal is enforced server-side; this only
   *  lets the UI avoid offering an action that would be refused. */
  requests_allowed: boolean;
}

/** This request's place in its month, computed server-side.
 *
 *  `consumed_by_request` is 0 unless the request is APPROVED, so the detail page
 *  never presents a pending, rejected or cancelled request as having spent hours.
 *  `remaining_if_approved` is non-null only while pending. */
export interface PermissionRequestBalance {
  month: string;
  allowance_hours: number;
  approved_hours: number;
  remaining_hours: number;
  consumed_by_request: number;
  remaining_before_request: number;
  remaining_if_approved: number | null;
}

/** `GET /permission-requests/{id}` - the detail page's single call. Names come
 *  from the server because the employee list endpoint is manager-scoped. */
export interface PermissionRequestDetail extends PermissionRequest {
  employee_name: string | null;
  employee_code: string | null;
  reviewer_name: string | null;
  balance: PermissionRequestBalance;
}

/** `GET /permission-requests/history` - one calendar month of rows AND that
 *  month's balance, from one set of server-computed month bounds. */
export interface PermissionHistory {
  employee_id: string;
  month: string;
  balance: PermissionBalance;
  items: PermissionRequest[];
  total: number;
}

export interface PermissionListParams {
  employee_id?: string;
  status?: PermissionStatus | "";
  from?: string;
  to?: string;
  limit: number;
  offset: number;
  /** Drop the caller's own requests - what the review queue passes, since nobody
   *  may review their own. Enforced server-side either way. */
  exclude_self?: boolean;
}

export const PERMISSION_STATUS_LABEL: Record<PermissionStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
  cancellation_requested: "Cancellation requested",
};

export const PERMISSION_DURATION_LABEL: Record<number, string> = {
  1: "1 hour",
  2: "2 hours",
};

// ---------- pure helpers ----------------------------------------------------

/** `4h` - the form the KPI, the dialog and the history table all use. */
export function formatHours(hours: number): string {
  return `${hours}h`;
}

/** `1hr` / `2hr` - the compact form used in a table cell beside a status. */
export function formatDuration(hours: number): string {
  return `${hours}hr`;
}

/**
 * The actual selected option, e.g. "1st Half - 1 Hour" - what the request
 * dialog, the detail page and the history/review tables all show. Falls back
 * to the plain compact form only for a request filed before Phase 4C, which
 * has no period on record and none that could be safely guessed.
 */
export function formatPermissionDuration(
  req: Pick<PermissionRequest, "period" | "duration_hours">,
): string {
  if (req.period) return PERMISSION_PERIOD_LABEL[req.period];
  return formatDuration(req.duration_hours);
}

/**
 * What the balance would be if this request were approved right now.
 *
 * Clamped at zero so an over-large selection previews `0h` rather than a
 * negative figure. It is a PREVIEW: the backend re-derives the balance under a
 * lock on every approval, so this can be stale or wrong without any risk of an
 * over-spend - never treat it as a check.
 */
export function remainingAfter(remainingHours: number, durationHours: number): number {
  return Math.max(0, remainingHours - durationHours);
}

/**
 * Whether a duration may be offered at all, given what is left this month.
 *
 * With 1h remaining, 1h is offered and 2h is not. The backend enforces the same
 * rule on approval; this only decides what the dropdown renders.
 */
export function isDurationAffordable(
  durationHours: number,
  remainingHours: number,
): boolean {
  return durationHours <= remainingHours;
}

/** `YYYY-MM-DD` for a Date in the given zone. CoreOps runs on the Chennai
 *  business calendar, so a default date must not come from a UTC clock.
 *  Same helper, same reason, as `leave/types.ts`. */
export function businessToday(
  now: Date = new Date(),
  timeZone = "Asia/Kolkata",
): string {
  // en-CA formats as YYYY-MM-DD, which compares correctly as a plain string.
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

// ---------- routes ----------------------------------------------------------
//
// Named once because four places navigate here - the KPI card's History link, the
// same link inside the request dialog, the detail page's back link, and the rows
// of the history table itself. A literal repeated four times is a literal that
// eventually disagrees with itself.

/** The employee's own monthly permission history.
 *
 *  Deliberately carries NO month parameter: opening it fresh must always land on
 *  the current month. The page keeps the selected month in `pm_month`, which
 *  `useUrlState` strips from the URL whenever it equals the current month, so a
 *  bare path is the current month by construction. */
export const PERMISSION_HISTORY_PATH = "/attendance/permission";

/** One permission request's detail page. */
export function permissionDetailPath(id: string): string {
  return `${PERMISSION_HISTORY_PATH}/${id}`;
}

// ---------- month navigation (pure string arithmetic) ------------------------
//
// Months are carried as `YYYY-MM-DD` on the first of the month, which is exactly
// what the `month` query parameter takes, so the URL value is passed to the API
// untransformed. All of it is integer/string maths rather than Date arithmetic:
// `new Date("2026-08-01")` parses as UTC midnight, so a browser behind UTC would
// step to the wrong month. There is no clock in here at all except `businessToday`.

const MONTH_RE = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/;

const MONTH_NAMES = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
] as const;

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
] as const;

function pad(n: number): string {
  return String(n).padStart(2, "0");
}

/** The first of the month containing `value`, as `YYYY-MM-DD`. */
export function monthStart(value: string): string {
  const m = MONTH_RE.exec(value);
  if (!m) return monthStart(businessToday());
  return `${m[1]}-${m[2]}-01`;
}

/** The current business month, as `YYYY-MM-DD` on the 1st. */
export function currentBusinessMonth(now: Date = new Date()): string {
  return monthStart(businessToday(now));
}

/** `delta` months from `monthValue`, rolling the year over correctly. */
export function shiftMonth(monthValue: string, delta: number): string {
  const m = MONTH_RE.exec(monthStart(monthValue));
  if (!m) return monthValue;
  // Work in absolute months so December -> January and January -> December both
  // fall out of the same arithmetic.
  const total = Number(m[1]) * 12 + (Number(m[2]) - 1) + delta;
  return `${String(Math.floor(total / 12)).padStart(4, "0")}-${pad((total % 12) + 1)}-01`;
}

/** `August 2026` - the month heading. */
export function formatMonthLabel(monthValue: string): string {
  const m = MONTH_RE.exec(monthValue);
  if (!m) return monthValue;
  return `${MONTH_NAMES[Number(m[2]) - 1]} ${m[1]}`;
}

/** `17 Aug 2026` - a date in a history row or a detail field. */
export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return value;
  return `${m[3]} ${MONTH_SHORT[Number(m[2]) - 1]} ${m[1]}`;
}

/** `2h / 4h` - consumed against the month's allowance, shown above the table. */
export function formatAvailable(remainingHours: number, allowanceHours: number): string {
  return `${formatHours(remainingHours)} / ${formatHours(allowanceHours)}`;
}

// ---------- detail-page action visibility -----------------------------------

/** Whether to offer Approve/Reject on the detail page.
 *
 *  `isReviewer` is passed in rather than derived from a role, because a
 *  permission is reviewable by a project manager AND by the routed Project Head
 *  (Phase 4B) - and Head-ness is not a role, it is per-project and comes from the
 *  report scope, exactly as `canReviewLeave` takes it. Beyond that the rule is
 *  unchanged: still pending, and NOT the reviewer's own request - a PM and a Head
 *  are both employees who file their own. The backend refuses each case
 *  independently; this only decides what renders. */
export function canReviewPermission(
  req: Pick<PermissionRequest, "status" | "employee_id">,
  isReviewer: boolean,
  myEmployeeId: string | null | undefined,
): boolean {
  if (!isReviewer) return false;
  if (req.status !== "pending") return false;
  return !myEmployeeId || req.employee_id !== myEmployeeId;
}

/** Whether to offer the ONE-STEP "Cancel" on a row.
 *
 *  The author's own PENDING request only. Withdrawing something nobody has
 *  granted yet has nothing to review, so it stays a single step - but an
 *  APPROVED permission is a granted absence and now goes through
 *  `canRequestPermissionCancellation` and a reviewer instead (Phase 4E), which
 *  is why `approved` no longer appears here. The backend enforces the same
 *  split; this only decides what renders. */
export function canCancelPermission(
  req: Pick<PermissionRequest, "status" | "employee_id" | "permission_date">,
  myEmployeeId: string | null | undefined,
): boolean {
  if (!myEmployeeId || req.employee_id !== myEmployeeId) return false;
  return req.status === "pending";
}

// ---------- cancellation of an APPROVED permission (Phase 4E) ----------------

/** Whether the author may ask to withdraw this approved permission.
 *
 *  Own request, still `approved`, and its day has not passed - a finished
 *  absence has nothing left to withdraw, and correcting the record afterwards is
 *  an attendance job. Exactly the rule the backend's
 *  `request_permission_cancellation` enforces. */
export function canRequestPermissionCancellation(
  req: Pick<PermissionRequest, "status" | "employee_id" | "permission_date">,
  myEmployeeId: string | null | undefined,
  today: string = businessToday(),
): boolean {
  if (!myEmployeeId || req.employee_id !== myEmployeeId) return false;
  return req.status === "approved" && req.permission_date >= today;
}

/** What the Permission History "Cancellation" cell shows for one row.
 *
 *    "request"    offer the Request cancellation action
 *    "requested"  a withdrawal is already awaiting review - this is what stops
 *                 a duplicate being filed from the UI (the backend refuses one
 *                 outright with a 409 regardless)
 *    "none"       nothing to say: a pending, rejected or already-cancelled row,
 *                 an approved one whose day has gone, or somebody else's
 *
 *  Deliberately says nothing about a `cancelled` row: the Status column beside
 *  it already reads "Cancelled", and repeating that here would be two columns
 *  saying one thing. */
export type PermissionCancellationCell = "request" | "requested" | "none";

export function permissionCancellationCell(
  req: Pick<PermissionRequest, "status" | "employee_id" | "permission_date">,
  myEmployeeId: string | null | undefined,
  today: string = businessToday(),
): PermissionCancellationCell {
  if (req.status === "cancellation_requested") return "requested";
  if (canRequestPermissionCancellation(req, myEmployeeId, today)) return "request";
  return "none";
}

/** Whether to offer the Approve/Reject cancellation controls.
 *
 *  `isReviewer` is passed in for the same reason `canReviewPermission` takes it:
 *  a permission is reviewable by a project manager AND by the routed Project
 *  Head, and Head-ness is not a role. Beyond that: a withdrawal actually
 *  awaiting a decision, and never the reviewer's own request. The backend
 *  re-checks the routed project on every decision. */
export function canReviewPermissionCancellation(
  req: Pick<PermissionRequest, "status" | "employee_id">,
  isReviewer: boolean,
  myEmployeeId: string | null | undefined,
): boolean {
  if (!isReviewer) return false;
  if (req.status !== "cancellation_requested") return false;
  return !myEmployeeId || req.employee_id !== myEmployeeId;
}
