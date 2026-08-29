export type LeaveType = "casual" | "sick" | "annual" | "comp_off" | "unpaid" | "other";
export type LeaveStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "cancelled"
  | "cancellation_requested";

export interface LeaveRequest {
  id: string;
  employee_id: string;
  employee_name: string | null;
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  /** Days the office is actually open across [start_date, end_date] - the
   *  number the employee is charged. Computed by the backend against the
   *  company calendar (weekends, working Saturdays, holidays and working-day
   *  overrides); never recalculated here. */
  working_days: number;
  reason: string | null;
  status: LeaveStatus;
  manager_id: string | null;
  manager_comment: string | null;
  routed_project_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestPage {
  items: LeaveRequest[];
  total: number;
  limit: number;
  offset: number;
}

export interface LeaveRequestCreateBody {
  leave_type: LeaveType;
  start_date: string;
  end_date: string;
  reason?: string | null;
}

export interface LeaveRequestUpdateBody {
  leave_type?: LeaveType;
  start_date?: string;
  end_date?: string;
  reason?: string | null;
}

export interface LeaveReviewBody {
  comment?: string | null;
}

/** One Planned deliverable conflicting with a leave request (decision support). */
export interface DeliverableConflict {
  deliverable_id: string;
  deliverable_name: string;
  project_id: string;
  project_name: string | null;
  project_code: string | null;
  status: string;
  target_date: string | null;
  employee_id: string;
  employee_name: string | null;
}

export interface LeaveDeliverableImpact {
  leave_request_id: string;
  conflicts: DeliverableConflict[];
}

export interface DeliverableImpactResponse {
  items: LeaveDeliverableImpact[];
}

/** Read-only summary of attendance already recorded across a leave request's
 *  dates. Shown in the PM cancellation queue; nothing here is ever written. */
export type AttendanceSummaryCode =
  | "present"
  | "leave"
  | "absent"
  | "half_day"
  | "holiday"
  | "weekend"
  | "comp_off"
  | "mixed"
  | "none";

export interface LeaveAttendanceSummary {
  leave_request_id: string;
  summary: AttendanceSummaryCode | string;
  days_recorded: number;
}

export interface AttendanceSummaryResponse {
  items: LeaveAttendanceSummary[];
}

export const ATTENDANCE_SUMMARY_LABEL: Record<string, string> = {
  present: "Present recorded",
  leave: "Leave recorded",
  absent: "Absent recorded",
  half_day: "Half day recorded",
  holiday: "Holiday recorded",
  weekend: "Weekend recorded",
  comp_off: "Comp off recorded",
  mixed: "Multiple statuses",
  none: "No attendance",
};

export function attendanceSummaryLabel(code: string | undefined): string {
  if (!code) return ATTENDANCE_SUMMARY_LABEL.none;
  return ATTENDANCE_SUMMARY_LABEL[code] ?? "Attendance recorded";
}

export interface LeaveListParams {
  employee_id?: string;
  status?: LeaveStatus | "";
  from?: string;
  to?: string;
  limit: number;
  offset: number;
  exclude_self?: boolean;
}

// Full label map — keeps `sick`/`unpaid` so any historical requests still
// render correctly even though they're no longer offered when filing a new one.
export const LEAVE_TYPE_LABEL: Record<LeaveType, string> = {
  casual: "Casual",
  sick: "Sick",
  annual: "Annual",
  comp_off: "Comp Off",
  unpaid: "Unpaid",
  other: "Other",
};

// Selectable types when filing a leave request (Casual / Annual / Comp Off / Other).
// `sick` and `unpaid` are intentionally excluded — display-only legacy values.
export const SELECTABLE_LEAVE_TYPES = ["casual", "annual", "comp_off", "other"] as const;

export type SelectableLeaveType = (typeof SELECTABLE_LEAVE_TYPES)[number];

export const LEAVE_TYPES: LeaveType[] = [...SELECTABLE_LEAVE_TYPES];

export const LEAVE_STATUS_LABEL: Record<LeaveStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
  cancellation_requested: "Cancellation Requested",
};

/** `YYYY-MM-DD` for a Date in the given zone. CoreOps runs on the Chennai
 *  business calendar, so "today" must not come from a UTC clock. */
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

function isOwn(
  req: Pick<LeaveRequest, "employee_id">,
  myEmployeeId: string | null | undefined,
): boolean {
  return !!myEmployeeId && req.employee_id === myEmployeeId;
}

/** Whether to offer "Cancel Request" on a row. Only the employee who filed a
 *  still-pending request may cancel it; approved leave goes through the
 *  manager. The backend enforces the same rule — this only decides rendering. */
export function canCancelLeave(
  req: Pick<LeaveRequest, "status" | "employee_id">,
  myEmployeeId: string | null | undefined,
): boolean {
  return req.status === "pending" && isOwn(req, myEmployeeId);
}

/** Whether to offer "Request Cancellation". Approved leave stays eligible for
 *  as long as any of it is still ahead — an employee who returned to work
 *  partway through an absence needs to withdraw the remainder. */
export function canRequestLeaveCancellation(
  req: Pick<LeaveRequest, "status" | "employee_id" | "end_date">,
  myEmployeeId: string | null | undefined,
  today: string = businessToday(),
): boolean {
  return req.status === "approved" && isOwn(req, myEmployeeId) && req.end_date >= today;
}

// ---------- PM leave queues (inner tabs of the Leave tab) -------------------

// `permission` is the 1h/2h permission queue (Phase 11). It lives here rather
// than as another Attendance tab because a permission is a smaller absence than
// leave, not a different kind of thing - and adding a top-level nav item for it
// was explicitly out of scope.
export const LEAVE_QUEUES = ["pending", "cancellation", "permission", "all"] as const;

export type LeaveQueue = (typeof LEAVE_QUEUES)[number];

/** Resolve the `queue` URL parameter. Anything unrecognised (a stale link, a
 *  hand-edited URL) falls back to the pending queue rather than erroring. */
export function resolveLeaveQueue(raw: string | null | undefined): LeaveQueue {
  return (LEAVE_QUEUES as readonly string[]).includes(raw ?? "")
    ? (raw as LeaveQueue)
    : "pending";
}

/** The list params a queue's TAB BADGE counts with.
 *
 *  `limit: 1` because only `total` is read - the badge never renders rows. The
 *  point of this helper is `exclude_self`: the badge and the list it labels must
 *  describe ONE dataset, and they drifted apart because the count call sites
 *  simply forgot to pass it. A Project Head reviewing their own queue sees their
 *  own requests filtered out of the list, so they must be filtered out of the
 *  number on the tab too - otherwise the tab says "1" and opens on an empty
 *  table. Both the badge and the queue's own list now build their
 *  `exclude_self` from the same flag, so the two cannot disagree again. */
export function leaveQueueCountParams(
  status: LeaveStatus,
  excludeSelf: boolean,
): LeaveListParams {
  return { status, limit: 1, offset: 0, exclude_self: excludeSelf };
}

/** The Duration line on Leave Detail: `3 days`, `1 day`, `0 days`.
 *
 *  Takes the backend's `working_days` and does nothing but pluralise it. The
 *  page used to derive the number itself as `(end - start) + 1`, which counted
 *  the Sundays, the 2nd/4th Saturdays and the company holidays inside a range
 *  and so disagreed with what the approval actually charged - 28-31 August 2026
 *  showed 4 where the backend deducts 3. There is no calendar arithmetic on this
 *  side of the wire any more; the backend is the only place that rule lives. */
export function formatLeaveDuration(workingDays: number): string {
  return `${workingDays} ${workingDays === 1 ? "day" : "days"}`;
}

/** `3 August 2026`, or `29 July 2026 - 30 July 2026` for a range. */
export function formatLeavePeriod(startDate: string, endDate: string): string {
  const start = formatLongDate(startDate);
  return startDate === endDate ? start : `${start} - ${formatLongDate(endDate)}`;
}

function formatLongDate(value: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  if (!m) return value;
  // Built as a local date so the day never shifts across the UTC boundary.
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
