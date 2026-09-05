/** Normal (<= 3 working days) or Special (> 3). Derived by the backend from
 *  `working_days` and never chosen by the employee - see
 *  `backend/app/modules/leave/classification.py`. The old Casual/Sick/Annual/
 *  Comp Off/Unpaid categories no longer exist. */
export type LeaveClassification = "normal" | "special";

/** Which half of a single working day a half-day leave covers, or `null` for
 *  the ordinary full-day leave every request was before migration 0084. Mirrors
 *  `backend/app/modules/leave/models.py::LeaveHalfDayPeriod`. The member names
 *  are storage and are never rendered - `LEAVE_HALF_DAY_LABEL` is. */
export type LeaveHalfDayPeriod = "first_half" | "second_half";

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
  start_date: string;
  end_date: string;
  /** Days the office is actually open across [start_date, end_date] - the
   *  number the employee is charged. Computed by the backend against the
   *  company calendar (weekends, working Saturdays, holidays and working-day
   *  overrides); never recalculated here. */
  working_days: number;
  /** Normal or Special, derived by the backend from `working_days`. */
  classification: LeaveClassification;
  /** Which half of the day this leave covers, or null for a full-day leave.
   *  Chosen by the employee in the Leave Request dialog and stored on the row -
   *  unlike `classification`, which is derived and never chosen. */
  half_day_period: LeaveHalfDayPeriod | null;
  reason: string | null;
  status: LeaveStatus;
  manager_id: string | null;
  /** The reviewer who approved or rejected the request, by name - resolved by
   *  the backend from the `manager_id` it stamps at decision time. Null until
   *  somebody has ruled, and on the responses mutations return. Read through
   *  `leaveDecisionActor`, never directly: a request approved and later
   *  cancelled still carries its approver here. */
  manager_name: string | null;
  manager_comment: string | null;
  routed_project_id: string | null;
  /** Who the request WENT TO, by name - a separate fact from `manager_name`,
   *  which is who decided it. While pending the backend derives it from the
   *  routed project's current Head, else the requester's reporting PM, through
   *  the same chain that delivers the submission notification; once approved or
   *  rejected it reads the submission notification actually delivered, so a Head
   *  reassigned since cannot rewrite history. DETAIL endpoint only - null on
   *  list rows and on the cancellation statuses. Read through `leaveActorRows`. */
  routed_to_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface LeaveRequestPage {
  items: LeaveRequest[];
  total: number;
  limit: number;
  offset: number;
}

/** `GET /leave-requests/classification-preview` - what a range costs and is
 *  classified as, asked while the employee is still choosing dates. */
export interface LeaveClassificationPreview {
  start_date: string;
  end_date: string;
  working_days: number;
  classification: LeaveClassification;
}

export interface LeaveRequestCreateBody {
  start_date: string;
  end_date: string;
  /** Present ONLY on a half-day request, where `start_date === end_date`. Its
   *  absence is what makes a request a full-day one, so every existing caller
   *  keeps working by saying nothing. Built by `leaveCreateBody`. */
  half_day_period?: LeaveHalfDayPeriod;
  reason?: string | null;
}

export interface LeaveRequestUpdateBody {
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

// The only two classifications there are. Still not selectable: the backend
// derives the value from the request's working days, historical rows included.
export const LEAVE_CLASSIFICATION_LABEL: Record<LeaveClassification, string> = {
  normal: "Normal",
  special: "Special",
};

/** The exact wording each half is shown as, and the ONLY wording either is ever
 *  shown as. Character-for-character identical to
 *  `backend/app/modules/leave/models.py::HALF_DAY_PERIOD_LABELS`, so the form
 *  and the backend cannot disagree about what the employee picked. */
export const LEAVE_HALF_DAY_LABEL: Record<LeaveHalfDayPeriod, string> = {
  first_half: "Half Day (First)",
  second_half: "Half Day (Second)",
};

/** What a half-day leave's duration reads as. Singular "day" on purpose - half
 *  of one day is not "0.5 days". Mirrors
 *  `backend/app/modules/leave/models.py::HALF_DAY_DURATION_LABEL`. */
export const LEAVE_HALF_DAY_DURATION = "0.5 day";

/**
 * THE TYPE A READER SEES, composed from both facts, in one place.
 *
 * THE DISPLAY PRECEDENCE, and the whole of it:
 *
 *   half_day_period === "first_half"   ->  "Half Day (First)"
 *   half_day_period === "second_half"  ->  "Half Day (Second)"
 *   otherwise                          ->  Normal / Special, exactly as today
 *
 * A half-day request HAS a classification - one working day is <= 3, so the
 * backend classifies it Normal - and that is precisely the bug this exists to
 * stop. Every Type cell on this side read `LEAVE_CLASSIFICATION_LABEL[
 * req.classification]` directly, so a request the employee filed as Half Day
 * (First) was listed, opened and reviewed as "Normal". The half is the more
 * specific fact and wins; the Normal/Special system is untouched underneath and
 * still decides every request that has no half.
 *
 * Both label maps are the ones their owners already export, so no wording is
 * respelled here. Mirrors `models.py::leave_type_label` on the backend, which
 * composes the same two facts for the emails.
 */
export function leaveTypeLabel(
  req: Pick<LeaveRequest, "classification" | "half_day_period">,
): string {
  if (req.half_day_period) return LEAVE_HALF_DAY_LABEL[req.half_day_period];
  return LEAVE_CLASSIFICATION_LABEL[req.classification];
}

// ---------- the Leave Request dialog's "Leave type" dropdown ----------------

/**
 * The four entries of the Leave type dropdown, in the order they are offered.
 *
 * WHAT THIS SELECTION ACTUALLY IS. It picks the SHAPE OF THE REQUEST, not a
 * label the backend is told to apply:
 *
 *   normal / special       a full-day leave. From + To, multi-day allowed, and
 *                          the backend classifies it from the working days the
 *                          dates cost - exactly as it always has. Picking
 *                          "Normal" for a fortnight files a Special leave, and
 *                          `leaveClassificationNote` says so on screen while the
 *                          form is still open, so the choice never becomes a
 *                          promise the saved request breaks.
 *   first_half /           a half-day leave. ONE date, sent as
 *   second_half            `start_date === end_date` with `half_day_period` set.
 *
 * The half entries are the only ones that add anything to the payload; the two
 * full-day entries send precisely the body the dialog has always sent.
 */
export const LEAVE_TYPE_CHOICES = [
  "normal",
  "special",
  "first_half",
  "second_half",
] as const;

export type LeaveTypeChoice = (typeof LEAVE_TYPE_CHOICES)[number];

export const LEAVE_TYPE_CHOICE_LABEL: Record<LeaveTypeChoice, string> = {
  normal: LEAVE_CLASSIFICATION_LABEL.normal,
  special: LEAVE_CLASSIFICATION_LABEL.special,
  first_half: LEAVE_HALF_DAY_LABEL.first_half,
  second_half: LEAVE_HALF_DAY_LABEL.second_half,
};

/** Whether this choice asks for ONE date rather than a From/To pair. Also the
 *  type guard that turns the choice into the `half_day_period` it is - the two
 *  half choices are deliberately named for the enum values they send, so no
 *  lookup table can drift out of step with them. */
export function isHalfDayChoice(
  choice: LeaveTypeChoice,
): choice is LeaveHalfDayPeriod {
  return choice === "first_half" || choice === "second_half";
}

/** The dialog's raw fields. Both date shapes are kept side by side rather than
 *  sharing one input, so switching the dropdown back and forth does not destroy
 *  what the employee already typed into the other. */
export interface LeaveFormValues {
  leave_type: LeaveTypeChoice;
  start_date: string;
  end_date: string;
  half_day_date: string;
  reason: string;
}

/**
 * The request body for the current form state - the one place the dropdown
 * turns into a payload.
 *
 * A half-day choice collapses to its single date on BOTH ends, which is the
 * rule the schema and the `leave_half_day_is_one_day` check constraint both
 * enforce; the From/To pair is ignored entirely, so a range typed before the
 * dropdown was switched cannot leak into a half-day request. A full-day choice
 * sends no half-day key at all - byte for byte the body this dialog has always
 * sent.
 */
export function leaveCreateBody(values: LeaveFormValues): LeaveRequestCreateBody {
  const reason = values.reason.trim() || null;
  if (isHalfDayChoice(values.leave_type)) {
    return {
      start_date: values.half_day_date,
      end_date: values.half_day_date,
      half_day_period: values.leave_type,
      reason,
    };
  }
  return {
    start_date: values.start_date,
    end_date: values.end_date,
    reason,
  };
}

/**
 * The line under the dropdown telling the employee what a full-day request will
 * actually be filed as.
 *
 * THIS IS WHY PICKING "Normal" IS NOT A LIE. Normal/Special remains the
 * backend's decision, derived from what the dates cost against the company
 * calendar - so the dropdown cannot be allowed to imply otherwise. The note
 * reports the server's own live answer for the dates currently in the form,
 * which is the same number and the same rule the saved request will get.
 *
 * Null when there is nothing truthful to say: no dates chosen yet (the preview
 * is disabled until both are present and in order), or a half-day choice, which
 * is one date and carries its own label already.
 */
export function leaveClassificationNote(
  choice: LeaveTypeChoice,
  preview: Pick<LeaveClassificationPreview, "working_days" | "classification"> | undefined,
): string | null {
  if (isHalfDayChoice(choice) || !preview) return null;
  const days = `${preview.working_days} working ${preview.working_days === 1 ? "day" : "days"}`;
  const label = LEAVE_CLASSIFICATION_LABEL[preview.classification];
  return `These dates cost ${days} - this will be filed as ${label} Leave.`;
}

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

/** Whether to offer Approve/Reject on the leave detail page.
 *
 *  `isReviewer` is passed in rather than derived from a role, because leave is
 *  reviewable by a project manager AND by a Project Head - and Head-ness is not
 *  a role, it is per-project and comes from the report scope (see
 *  `leave-tab.tsx`). Beyond that the rule matches the permission detail page:
 *  still pending, and not the reviewer's own request - a PM and a Head are both
 *  employees who file their own leave. The backend refuses each case
 *  independently; this only decides what renders. */
export function canReviewLeave(
  req: Pick<LeaveRequest, "status" | "employee_id">,
  isReviewer: boolean,
  myEmployeeId: string | null | undefined,
): boolean {
  if (!isReviewer) return false;
  if (req.status !== "pending") return false;
  return !myEmployeeId || req.employee_id !== myEmployeeId;
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

// ---------- A Project Head's My leave / Team approvals switch ---------------

export const LEAVE_VIEWS = ["my", "team"] as const;

export type LeaveView = (typeof LEAVE_VIEWS)[number];

/** Resolve the `view` URL parameter for a Project Head's Leave tab.
 *
 *  An explicit `view` always wins, and it is what Back restores: both choices
 *  are written into the URL, so neither has to be inferred from anything else.
 *
 *  `hasQueue` only covers the links that predate that parameter - chiefly the
 *  PM/Head dashboard shortcut, which names a QUEUE and no view. A queue is a
 *  Team approvals queue, so those links still open on Team approvals. Nothing
 *  else infers it. (Leave notifications no longer rely on this: they deep-link
 *  to the request's detail page and name `view` explicitly in their `from`.) */
export function resolveLeaveView(
  raw: string | null | undefined,
  hasQueue: boolean,
): LeaveView {
  if ((LEAVE_VIEWS as readonly string[]).includes(raw ?? "")) return raw as LeaveView;
  return hasQueue ? "team" : "my";
}

// ---------- Leave list -> Leave detail -> back to the SAME list -------------

/** Where "← Leave Requests" goes when the detail page was opened cold (an email link, a
 *  bookmark, a pasted URL). Exactly what that link has always done. */
export const LEAVE_LIST_HREF = "/attendance?tab=leave";

/** The detail page's "which list did I come from" parameter. */
export const LEAVE_RETURN_PARAM = "from";

/**
 * The detail URL for one request, carrying the list it is being opened FROM.
 *
 * `from` is the caller's own current URL, so it already encodes whatever that
 * list was showing - `view=team`, `queue=cancellation`, a month, a page. This
 * function does not know or care which: it round-trips the address instead of
 * rebuilding it, which is why My leave, the three approval queues and any future
 * queue all come back correctly without a case each.
 *
 * Omitted when there is nothing to return to, so the detail URL stays exactly as
 * short as it is today for callers that have no list behind them.
 */
export function leaveDetailHref(
  requestId: string,
  from?: string | null,
): string {
  const base = `/attendance/leave/${requestId}`;
  const target = (from ?? "").trim();
  return target
    ? `${base}?${LEAVE_RETURN_PARAM}=${encodeURIComponent(target)}`
    : base;
}

/**
 * Resolve the `from` parameter back into the href "← Leave Requests" points at.
 *
 * Accepted only when it is the Attendance page itself - the one page a Leave
 * list can live on. A `from` is a convenience the app writes for itself, never
 * a destination a hand-edited or forwarded URL gets to choose, so anything else
 * (another route, an absolute URL, a protocol-relative `//host`, a look-alike
 * like `/attendance-x`) falls back to the plain Leave list rather than being
 * followed. Deep links that carry no `from` at all take that same fallback,
 * which is precisely the behaviour they have today.
 */
export function leaveReturnHref(raw: string | null | undefined): string {
  const target = (raw ?? "").trim();
  const [path] = target.split("?");
  return path === "/attendance" ? target : LEAVE_LIST_HREF;
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

/**
 * The Duration line for ONE request: `0.5 day` for a half day, otherwise the
 * working-day count exactly as `formatLeaveDuration` has always rendered it.
 *
 * A half-day request covers one working day, so `working_days` is honestly 1 -
 * and "1 day" against a request filed as half a day is what the reader reported
 * as wrong. This is the only place the two disagree, and the request's own
 * stored half is what settles it; the count is still never computed here.
 *
 * Mirrors `models.py::leave_duration_label`.
 */
export function leaveRequestDuration(
  req: Pick<LeaveRequest, "working_days" | "half_day_period">,
): string {
  if (req.half_day_period) return LEAVE_HALF_DAY_DURATION;
  return formatLeaveDuration(req.working_days);
}

/**
 * The "By" column of the All-leave table: who ruled on this request.
 *
 * ONLY A SETTLED DECISION HAS AN ACTOR. Approved and rejected name the reviewer
 * who took that decision; every other status returns null and the table renders
 * an em dash:
 *
 *   pending                 nobody has decided yet
 *   cancellation_requested  the standing approval is under review again
 *   cancelled               deliberately blank (Phase 3 section 7)
 *
 * `cancelled` is the case worth stating, because the underlying row is NOT
 * blank. A leave that was approved and then withdrawn keeps its approver in
 * `manager_id` - that is the honest record of what happened - and the
 * cancellation itself is a DIFFERENT act by a DIFFERENT person, which nothing
 * currently records. Showing the approver's name against "Cancelled" would
 * therefore name the wrong actor, so this returns null rather than guessing; the
 * cancellation actor is out of scope for this phase.
 *
 * Null is also what an un-named actor gives: a request decided before the id was
 * recorded, or one whose reviewer's employee row has since gone.
 */
export function leaveDecisionActor(
  req: Pick<LeaveRequest, "status" | "manager_name">,
): string | null {
  if (req.status !== "approved" && req.status !== "rejected") return null;
  return req.manager_name?.trim() || null;
}

/**
 * The actor/routing rows the Leave Request card shows under Status, in order.
 *
 * TWO SEPARATE FACTS, AND A SETTLED REQUEST HAS BOTH. "Routed to" is who the
 * request went to; "Approved by" / "Rejected by" is who actually ruled on it.
 * They are frequently different people - a request routed to a Project Head can
 * be decided by the PM - so one is never allowed to stand in for the other and
 * neither is derived from the other:
 *
 *   pending    Routed to
 *   approved   Routed to  +  Approved by
 *   rejected   Routed to  +  Rejected by
 *
 * Everything else returns an empty list and the card renders nothing between
 * Status and the Note row:
 *
 *   cancelled               the cancellation actor is NOT recorded anywhere.
 *                           `manager_id` on a cancelled row is its former
 *                           APPROVER, so "Cancelled ... by <approver>" would name
 *                           the wrong person. Unchanged from Phase 3.
 *   cancellation_requested  the standing approval is under review again; neither
 *                           question has a settled answer.
 *
 * Either row is dropped individually when its name is missing, so a request with
 * no recorded routing still names its approver and vice versa.
 *
 * INFORMATIONAL, NEVER PERMISSION. This is what the reader is TOLD, and it is
 * deliberately shown to the request owner too - an employee is entitled to know
 * who their request went to. What the reader may DO is `canReviewLeave`, which
 * is unrelated and unchanged: a Project Head looking at their own pending
 * request sees "Routed to ..." here and still gets no Review card.
 *
 * The decided row goes through `leaveDecisionActor` rather than reading
 * `manager_name` again, so the detail page and the All-leave "By" column cannot
 * disagree about which statuses have an actor.
 */
export interface LeaveActorRow {
  label: string;
  name: string;
}

export function leaveActorRows(
  req: Pick<LeaveRequest, "status" | "manager_name" | "routed_to_name">,
): LeaveActorRow[] {
  if (
    req.status !== "pending" &&
    req.status !== "approved" &&
    req.status !== "rejected"
  ) {
    return [];
  }
  const rows: LeaveActorRow[] = [];
  const routedTo = req.routed_to_name?.trim();
  if (routedTo) rows.push({ label: "Routed to", name: routedTo });
  const actor = leaveDecisionActor(req);
  if (actor) {
    rows.push({
      label: req.status === "approved" ? "Approved by" : "Rejected by",
      name: actor,
    });
  }
  return rows;
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
