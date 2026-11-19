/**
 * Rework Activity Approval - the employee-facing state of one report row.
 *
 * Pure (no React) so `node --test` can pin it. Two inputs only:
 *   requiresApproval - the selected sub-activity's requires_pm_approval flag
 *                      (Activity Master configuration, migration 0090);
 *   status           - the row's server-resolved rework_approval_status
 *                      (null until the report is submitted).
 *
 * The backend decides authoritatively at submit; this only labels it.
 */

export type ReworkApprovalStatus = "pending" | "approved" | "rejected" | "cancelled";

export type ReworkBadgeTone = "warning" | "success" | "danger";

export interface ReworkRowBadge {
  label: string;
  tone: ReworkBadgeTone;
}

/** Shown under the selectors before the report is submitted. */
export const PM_APPROVAL_REQUIRED_LABEL = "PM Approval Required";
export const PM_APPROVAL_REQUIRED_MESSAGE =
  "This activity requires Project Manager approval. Your report will be submitted for review.";

import { scaledTarget } from "./benchmark-target.ts";

// Mirrors activity-master's QUANTITY / TASK benchmark sets (legacy values
// included), kept local so this module stays dependency-free for node --test.
const QUANTITY_TYPES = new Set(["NUMERIC", "NUMERIC_DAILY", "TASK_WITH_QUANTITY"]);
const TASK_TYPES = new Set(["TASK_BASED", "TASK_STATUS_ONLY", "TASK_WITH_QUANTITY"]);

export interface CorrectionBenchmarkInput {
  benchmark_type: string | null;
  benchmark_value: number | string | null;
  benchmark_period_days: number | null;
  relevant_count_field: string | null;
}

export interface CorrectionBenchmark {
  /** Per-period quantity target under the count input; null = none. */
  target: number | null;
  /** The unit the target is counted in ("tags"...), quantity modes only. */
  unit: string | null;
  /** Task modes: show the "Mark task fully completed" tick. */
  showCompletion: boolean;
  /** Task modes: the allowed duration, for "Complete within N days". */
  periodDays: number | null;
}

/**
 * What the correction popup shows for the chosen sub-activity, the same rules
 * the report form uses:
 *   quantity (NUMERIC / NUMERIC_DAILY)  -> target under the count
 *   lumpsum  (TASK_STATUS_ONLY / legacy TASK_BASED) -> the completion tick
 *   TASK_WITH_QUANTITY                  -> both
 * The target is scaled to the row's day part (half day = half, rounded UP to
 * a whole unit), exactly as the backend freezes it at submit.
 */
export function correctionBenchmark(
  sub: CorrectionBenchmarkInput | undefined,
  dayPart: string | null | undefined,
): CorrectionBenchmark {
  if (!sub?.benchmark_type) {
    return { target: null, unit: null, showCompletion: false, periodDays: null };
  }
  const fraction = dayPart === "first_half" || dayPart === "second_half" ? 0.5 : 1;
  const isQuantity = QUANTITY_TYPES.has(sub.benchmark_type);
  const isTask = TASK_TYPES.has(sub.benchmark_type);
  return {
    target: isQuantity ? scaledTarget(sub.benchmark_value, fraction) : null,
    unit: isQuantity ? sub.relevant_count_field : null,
    showCompletion: isTask,
    periodDays: isTask ? sub.benchmark_period_days ?? null : null,
  };
}

/** The six unit columns, in the one order the app uses everywhere. */
const COUNT_COLUMNS = [
  "tags_count",
  "docs_count",
  "bom_count",
  "spares_count",
  "pages_count",
  "records_count",
] as const;
type CountColumn = (typeof COUNT_COLUMNS)[number];

export interface CorrectionSourceRow {
  project_id: string;
  project_code?: string | null;
  tags_count?: number;
  docs_count?: number;
  bom_count?: number;
  spares_count?: number;
  pages_count?: number;
  records_count?: number;
}

export interface CorrectionChoice {
  subActivityId: string;
  description: string;
  /** The column the main count goes in ("tags_count"...), or null for none. */
  countColumn: string | null;
  count: number | null;
  /** A lumpsum row names its own unit (count_field) beside the count. */
  lumpsumUnit: string | null;
  /** Task modes: the "Mark task fully completed" tick. */
  isCompleted?: boolean;
}

/**
 * The body for POST /rework-approvals/{id}/correct. The project stays the
 * rejected row's (its manual code is resent for a code-less project), the other
 * counts carry over untouched, and only the chosen sub-activity, remark and
 * main count change.
 */
export function buildCorrectionBody(row: CorrectionSourceRow, choice: CorrectionChoice) {
  const counts = Object.fromEntries(
    COUNT_COLUMNS.map((c) => [c, Number(row[c] ?? 0) || 0]),
  ) as Record<CountColumn, number>;
  const body: Record<string, unknown> = {
    project_id: row.project_id,
    manual_project_code: row.project_code ?? "",
    sub_activity_id: choice.subActivityId,
    description: choice.description.trim(),
    is_completed: choice.isCompleted === true,
    ...counts,
  };
  if (choice.lumpsumUnit) {
    if (choice.count !== null && choice.count > 0) {
      body.count_field = choice.lumpsumUnit;
      body.count_value = choice.count;
    }
  } else if (choice.countColumn && (COUNT_COLUMNS as readonly string[]).includes(choice.countColumn)) {
    body[choice.countColumn] = Math.max(0, choice.count ?? 0);
  }
  return body;
}

/**
 * One report's overall rework state, for the Reports table "R" marker.
 * Rejected outranks pending (it needs the employee's action), pending outranks
 * approved; null = no rework activity on the report (the slot stays blank).
 */
export function reportReworkState(
  tasks: ReadonlyArray<{ rework_approval_status?: string | null }> | null | undefined,
): "rejected" | "pending" | "approved" | null {
  const statuses = new Set((tasks ?? []).map((t) => t.rework_approval_status));
  if (statuses.has("rejected")) return "rejected";
  if (statuses.has("pending")) return "pending";
  if (statuses.has("approved")) return "approved";
  return null;
}

export function reworkRowBadge(
  requiresApproval: boolean,
  status: ReworkApprovalStatus | string | null | undefined,
): ReworkRowBadge | null {
  switch (status) {
    case "pending":
      return { label: "In Review", tone: "warning" };
    case "approved":
      return { label: "Approved", tone: "success" };
    case "rejected":
      return { label: "Rejected - Action Required", tone: "danger" };
    default:
      // Not submitted yet (or a cancelled cycle): only the configuration speaks.
      return requiresApproval ? { label: PM_APPROVAL_REQUIRED_LABEL, tone: "warning" } : null;
  }
}
