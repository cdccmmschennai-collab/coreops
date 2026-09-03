/**
 * Biometric employee mapping (Phase 5) - PM-only.
 *
 * Mirrors `app/modules/biometric/schemas.py`. Nothing here describes a session,
 * an IN/OUT state or a duration: punch-state semantics are still unresolved and
 * this module does not pretend otherwise.
 */

// The classification vocabulary is declared once, in `day-detail.ts`, and reused
// here - two copies of a status union eventually disagree.
import type { BiometricClassification } from "./day-detail";

export type { BiometricClassification };

export const PROVIDER_EASYTIME = "easytime";

export type CodeStatus = "mapped" | "unmapped";

/**
 * One distinct EasyTime code seen in the raw punch log.
 *
 * There is no suggested employee, here or in the API: the employee fields are
 * populated only when an active mapping row exists. A PM reads the code and
 * chooses - CoreOps never proposes a pairing.
 */
export interface ExternalCode {
  provider: string;
  external_employee_code: string;
  punch_count: number;
  first_seen: string;
  last_seen: string;
  status: CodeStatus;

  mapping_id: string | null;
  employee_id: string | null;
  employee_code: string | null;
  employee_name: string | null;
  verified_at: string | null;

  /** How many of this code's stored punches already carry an employee id.
   *  Mapping a code does NOT change this - raw punches are immutable. */
  attributed_punch_count: number;
  /** Would resolve at ingestion time by the exact employee_code fallback even
   *  without a mapping row. */
  resolves_by_exact_code: boolean;
}

export interface ExternalCodePage {
  items: ExternalCode[];
  total: number;
  limit: number;
  offset: number;
  /** Provider-wide, independent of the current filter/page. */
  total_codes: number;
  mapped_codes: number;
  unmapped_codes: number;
}

/**
 * One employee, one attendance day: the outer boundary of their punches.
 *
 * `first_in` / `last_out` are the earliest and latest punch of the IST day after
 * re-scan collapsing - NOT device-reported IN/OUT states, which EasyTime does not
 * send. `last_out` is null when only one punch survived: one sighting cannot be
 * both an arrival and a departure, and an OUT is never invented.
 *
 * This is observation shown beside attendance. It is not an attendance record.
 */
export interface DailySummary {
  employee_id: string;
  employee_code: string | null;
  employee_name: string | null;
  /** Attendance day in Asia/Kolkata, `YYYY-MM-DD`. */
  summary_date: string;
  first_in: string | null;
  last_out: string | null;
  /** "device" | "pm" | null - which value first_in/last_out came from. A
   *  PM-entered time only ever fills a boundary the device left empty; see
   *  the backend's `_merge_boundary`. Pure biometric evidence (punch_count,
   *  kept_count, punch_times below) is never affected by this. */
  first_in_source: "device" | "pm" | null;
  last_out_source: "device" | "pm" | null;
  /** Raw punches for the day, and how many survived collapsing. Debugging. */
  punch_count: number;
  kept_count: number;
  /** The surviving punches the boundary was taken from, so a human reviewer can
   *  check the derivation. Times only - never the raw device payload. */
  punch_times: string[];
  external_employee_codes: string[];

  /** Elapsed minutes between first_in and last_out. ONE session - no break
   *  deduction, no overtime. Null (not 0) when both boundaries do not exist. */
  worked_minutes: number | null;
  /** The employee's CONTRACTED window for this day, from their office row. */
  scheduled_start_at: string | null;
  scheduled_end_at: string | null;
  scheduled_minutes: number | null;
  /** `office` when the employee's office supplied the window, `default` when the
   *  backend fallback did. Shown rather than hidden. */
  shift_source: ShiftSource | null;
  /** The conservative verdict. NOT an attendance status: biometric evidence
   *  carries no cause, so half day / permission / leave / absent never appear. */
  classification: BiometricClassification;
  review_required: boolean;
  /** Stable slugs, most-decisive first. Some are verdicts
   *  (`short_of_scheduled_duration`), some are context that does not open a
   *  review on its own (`first_punch_after_shift_start`). */
  review_reasons: string[];

  /** Phase 12. APPROVED permission hours (1 or 2) for this employee-day, or
   *  null. Joined from `permission_requests`, never derived from punches, and
   *  an input to nothing above: the times, counts and `worked_minutes` are the
   *  same values they would be with no permission at all. */
  permission_hours: number | null;
}

/**
 * The four things biometric evidence can support, and no more.
 *
 * Mirrors `CLASSIFICATIONS` in `app/modules/biometric/constants.py`. Deliberately
 * NOT `AttendanceStatus`: every interesting value of that enum encodes a CAUSE
 * (half day, leave, holiday), and a punch stream cannot supply one. A 6-hour day
 * is `needs_review`, never "half day".
 */
export type ShiftSource = "office" | "default";

/** The employee's contracted office hours - CoreOps' own data, not biometric.
 *  Plain local TIME strings (`"09:30:00"`); never timezone-converted. */
export interface SummarySchedule {
  office_name: string | null;
  timezone: string | null;
  shift_start: string | null;
  shift_end: string | null;
  break_minutes: number | null;
}

export interface DailySummaryPage {
  items: DailySummary[];
  total: number;
  provider: string;
  date_from: string;
  date_to: string;
  /** How the boundary was derived; `anchor_earliest_latest` today. */
  derivation: string;
  /** False while EasyTime reports no usable punch direction. */
  punch_state_available: boolean;
  /** Set only when a single employee was requested and they have an office. */
  schedule: SummarySchedule | null;
  /** Minutes a day may fall short of its scheduled window and still count as
   *  `present`. Zero because the late-arrival grace period is an unanswered
   *  management question, not because zero is a rule. */
  grace_minutes: number;
}

/**
 * One employee's day on the PM review screen (Phase 8).
 *
 * Narrower than `DailySummary` on purpose: no punch counts, no punch times, no
 * derivation slug. This row answers "is this day settled, and if not why?" -
 * evidence inspection is a different question and a different screen.
 *
 * A row with `classification: "no_record"` means no biometric evidence exists
 * for that employee that day. It does NOT mean absent: the cause may be leave,
 * a permission, official duty or a missed punch, none of which are knowable from
 * punches. Phase 9 supplies that context.
 */
export interface DailyReviewRow {
  employee_id: string;
  employee_code: string | null;
  employee_name: string | null;

  first_in: string | null;
  last_out: string | null;
  worked_minutes: number | null;
  /** "device" | "pm" | null - which value this DISPLAYED boundary came from.
   *  A PM-entered time only ever fills a boundary the device did not record;
   *  biometric evidence itself is unaffected. */
  first_in_source: "device" | "pm" | null;
  last_out_source: "device" | "pm" | null;

  scheduled_start_at: string | null;
  scheduled_end_at: string | null;
  scheduled_minutes: number | null;

  classification: BiometricClassification;
  /** True only when the punches could not settle the day AND nobody has ruled on
   *  it. An official record clears it - that ruling is the missing information. */
  review_required: boolean;
  /** Whether the PM may supply this boundary. False when the device recorded it:
   *  biometric evidence is immutable, so only a missing punch is fillable. */
  can_set_check_in: boolean;
  can_set_check_out: boolean;
  /** Everything observed, including context-only notes. */
  review_reasons: string[];
  /** The subset that actually requires attention - what the UI shows. */
  blocking_reasons: string[];

  /** The OFFICIAL record, when a human has already ruled on this day. Null means
   *  nobody has decided yet - not that the employee was absent. Written only by
   *  the attendance module; biometric never touches it. */
  attendance_record_id: string | null;
  attendance_status: string | null;
  attendance_check_in_at: string | null;
  attendance_check_out_at: string | null;
  /** The reason the PM gave. Null when nobody explained the day. */
  attendance_note: string | null;
  /** How much of the day the leave pool paid for (migration 0083): 1, 0.5 or 0.
   *  Null means the day never stated one, which is every row written before
   *  that migration and is worth 0 on a half day. Carried so the decision dialog
   *  can seed its "Half-day leave" tick from the day itself rather than
   *  defaulting a company half day into charging leave on its next save. */
  attendance_leave_day_fraction?: number | null;

  /** Phase 12. APPROVED permission hours for this employee-day, or null. An
   *  attendance ATTRIBUTE shown beside `attendance_status` - it never replaces
   *  it, and it is never rendered as leave. */
  permission_hours: number | null;
}

/** Counts for the WHOLE day, before any filter. No leave/permission/half-day:
 *  those need approved-exception data that does not exist until Phase 9. */
export interface DailyReviewCounts {
  employees: number;
  review_required: number;
  present: number;
  incomplete: number;
  needs_review: number;
  no_record: number;
}

export interface DailyReviewPage {
  review_date: string;
  provider: string;
  items: DailyReviewRow[];
  /** Rows after filtering and pagination; `counts` always describes the
   *  unfiltered day. */
  total: number;
  limit: number;
  offset: number;
  counts: DailyReviewCounts;
}

export interface PunchEntry {
  punch_time: string;
  /** Only the first and last surviving punch of the day carry a boundary
   *  role; everything between is context, never a paired session. */
  role: "first_in" | "last_out" | "punch";
  /** Always "device" - a PM-entered boundary is never a punch row; see
   *  AttendanceDayDetail.row instead. */
  source: "device";
}

export interface AttendanceDayDetail {
  review_date: string;
  provider: string;
  row: DailyReviewRow;
  punches: PunchEntry[];
}

export interface EmployeeMapping {
  id: string;
  provider: string;
  external_employee_code: string;
  employee_id: string;
  employee_code: string | null;
  employee_name: string | null;
  is_active: boolean;
  verified_at: string | null;
  created_at: string;
  updated_at: string;
}

// POST /biometric/mappings/bulk exists server-side for a reviewed initial
// import, but no screen calls it: every mapping in the UI is made one code at a
// time through POST /biometric/mappings. Nothing is typed for it here on purpose.

/** One row of the employee picker. */
export interface EmployeeOption {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  status: string;
}

export interface EmployeePage {
  items: EmployeeOption[];
  total: number;
  limit: number;
  offset: number;
}
