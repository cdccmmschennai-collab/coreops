/**
 * Comp Off request types and the pure rules the Comp Off tab renders by.
 *
 * Import-free on purpose, like `attendance/tabs.ts`: the host-Node unit test
 * loads this file directly, and the repo has no DOM test harness, so everything
 * worth asserting about the tab lives here rather than inside JSX.
 *
 * Mirrors `backend/app/modules/comp_off/schemas.py`. Every rule below is a
 * CONVENIENCE for the form and the buttons - the backend re-checks all of them
 * (and eligibility, evidence and conflicts, which only it can see) on every call.
 */

export type CompOffStatus = "pending" | "approved" | "rejected" | "cancelled";

export interface CompOffRequest {
  id: string;
  employee_id: string;
  /** Server-resolved on list and detail reads; null on mutation responses. */
  employee_name: string | null;
  /** The non-working day the employee worked. */
  worked_date: string;
  /** The working day they take off in return. */
  off_date: string;
  reason: string | null;
  status: CompOffStatus;
  manager_id: string | null;
  manager_name: string | null;
  /** The approval note, or the rejection reason. */
  manager_comment: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CompOffRequestPage {
  items: CompOffRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface CompOffRequestCreateBody {
  worked_date: string;
  off_date: string;
  reason?: string | null;
}

export interface CompOffApproveBody {
  comment?: string | null;
}

export interface CompOffRejectBody {
  reason: string;
}

export interface CompOffListParams {
  status?: CompOffStatus | "";
  limit: number;
  offset: number;
  /** Drop the caller's own requests - what the review queue passes. */
  exclude_self?: boolean;
}

export const COMP_OFF_STATUSES: CompOffStatus[] = [
  "pending",
  "approved",
  "rejected",
  "cancelled",
];

export const COMP_OFF_STATUS_LABEL: Record<CompOffStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

/** Same colour language as the leave badge. */
export const COMP_OFF_STATUS_VARIANT: Record<
  CompOffStatus,
  "neutral" | "info" | "success" | "warning" | "danger"
> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  cancelled: "neutral",
};

export const COMP_OFF_PAGE_SIZE = 20;

// ---------- dates ------------------------------------------------------------

/** Today on the Chennai business calendar as `YYYY-MM-DD` - the same "today"
 *  the backend's `_today()` uses, so the form and the server agree on it. */
export function businessToday(now: Date = new Date(), timeZone = "Asia/Kolkata"): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(now);
}

const MONTH_SHORT = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

/** `2027-03-07` -> `07 Mar 2027`; a timestamp is shown by its date part. */
export function formatShortDate(value: string | null | undefined): string {
  if (!value) return "-";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (!m) return value;
  return `${m[3]} ${MONTH_SHORT[Number(m[2]) - 1]} ${m[1]}`;
}

/** `YYYY-MM-DD` shifted by whole days, in UTC so no local offset moves it. */
export function addDaysIso(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export interface CompOffDateErrors {
  worked_date?: string;
  off_date?: string;
}

/**
 * The date rules the form can check without the server. ISO dates compare
 * correctly as strings. Calendar eligibility (non-working worked day, working
 * day off), the work-report evidence and conflicts are server-only.
 */
export function validateCompOffDates(
  workedDate: string,
  offDate: string,
  today: string,
): CompOffDateErrors {
  const errors: CompOffDateErrors = {};
  if (!workedDate) errors.worked_date = "Choose the day you worked.";
  else if (workedDate > today) {
    errors.worked_date = "The day you worked can't be in the future.";
  }
  if (!offDate) errors.off_date = "Choose the day you want off.";
  else if (offDate <= today) {
    errors.off_date = "The day off must be after today - request it in advance.";
  }
  if (workedDate && offDate && workedDate === offDate) {
    errors.off_date = "The day off must be a different date from the day you worked.";
  }
  return errors;
}

export function hasErrors(errors: CompOffDateErrors): boolean {
  return Boolean(errors.worked_date || errors.off_date);
}

/** Trimmed rejection reason, or the message to show when it is blank. */
export function rejectionReasonError(reason: string): string | null {
  return reason.trim() ? null : "A reason is required to reject a comp off request.";
}

// ---------- who sees what ----------------------------------------------------

export interface CompOffViewer {
  role: string | undefined;
  employeeId: string | null | undefined;
}

export interface CompOffView {
  /** The request form and "My requests". Employee-linked non-managers only,
   *  exactly as `leave.request` gates the leave form. A Project Head is an
   *  employee here and files like one. */
  canRequest: boolean;
  /** The review queue and the all-requests list. Project managers only: comp off
   *  has no Project Head routing, and the backend refuses everyone else. */
  canReview: boolean;
}

export function compOffView({ role, employeeId }: CompOffViewer): CompOffView {
  const isPm = role === "project_manager";
  return { canRequest: Boolean(employeeId) && !isPm, canReview: isPm };
}

/** Whether to offer Approve / Reject on this row. Never one's own request, and
 *  only while pending - the server enforces both. */
export function canDecide(req: CompOffRequest, viewer: CompOffViewer): boolean {
  return (
    viewer.role === "project_manager" &&
    req.status === "pending" &&
    req.employee_id !== viewer.employeeId
  );
}

/** Whether to offer Cancel. Only the author's PENDING request - an approved
 *  request is final (no reversal policy exists yet). */
export function canCancel(req: CompOffRequest, viewer: CompOffViewer): boolean {
  return req.status === "pending" && Boolean(viewer.employeeId) &&
    req.employee_id === viewer.employeeId;
}

// ---------- detail page --------------------------------------------------------

/** The Comp Off tab of the Attendance page - where the detail page returns. */
export const COMP_OFF_TAB_HREF = "/attendance?tab=comp-off";

/** A request's detail page, a child of the Attendance page like
 *  `/attendance/leave/{id}`. */
export function compOffDetailHref(id: string): string {
  return `/attendance/comp-off/${id}`;
}

/** "Approved by" / "Rejected by" for a decided request, else null - a pending
 *  or cancelled request names no decision-maker. */
export function decidedByLabel(status: CompOffStatus): string | null {
  if (status === "approved") return "Approved by";
  if (status === "rejected") return "Rejected by";
  return null;
}

// ---------- errors -----------------------------------------------------------

/**
 * What to tell the user after a failed call, from the API error's status and
 * its (already user-facing) message. A 5xx or a network failure never shows the
 * server's text - only a generic retry line.
 */
export function compOffErrorMessage(
  status: number | undefined,
  message: string | undefined,
  action: string,
): string {
  if (status === 409) {
    return `${message || "This request changed while you were working on it."} ` +
      "Refresh the list to see its current state.";
  }
  if (status === 422 || status === 403 || status === 404) {
    return message || `Could not ${action}.`;
  }
  return `Could not ${action}. Please try again.`;
}
