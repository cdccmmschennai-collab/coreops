/**
 * How a work item presents itself — pure, no React. One Open Task card
 * (openTaskCardState) and one saved report row's "Overall task" badge
 * (overallTaskBadge) ask the same question of the same item, so they share
 * these helpers rather than each deriving the rule.
 *
 * The two kinds of open work item are measured by different clocks, and until
 * now the card showed only one of them:
 *
 *   * TASK_WITH_QUANTITY (and any other non-lump-sum task benchmark) has a
 *     CALENDAR deadline. "Due 2026-08-27" is exactly the value that decides
 *     whether it is overdue, so the card keeps saying it.
 *   * A LUMP-SUM activity is measured in WORK DAYS — the number of distinct
 *     report dates it has actually been worked on. Its `due_date` is a frozen
 *     historical snapshot that decides nothing about continuation any more, so
 *     showing "Due <a date in the past>" next to an activity that is still on
 *     day 2 of 3 is actively misleading. These cards show the work-day state
 *     instead: "Day 2 of 3" while the allowance holds, "Duration exceeded" once
 *     it is spent.
 *
 * The work-day arithmetic here mirrors backend work_items.lumpsum_lifecycle /
 * lumpsum_allowance_exhausted one for one, including the `max(1, target_days)`
 * clamp for a blank benchmark period. `days_used` counts the work days spent
 * BEFORE the report being written, so the report being written is day
 * days_used + 1.
 *
 * Work days are how much of the allowance is spent — NOT how long the activity
 * stays available. Every open item, lump-sum included, is confined by the
 * backend to the Friday-Thursday reporting week containing its start date, and
 * an activity re-picked in a later week is a new work item with a new
 * allowance. So a lump-sum card never survives a week boundary, and the
 * work-day state it shows is always state within one reporting week.
 */
import type { OpenTask } from "./types";

export type BadgeVariant = "neutral" | "warning" | "danger" | "success";

export interface OpenTaskCardState {
  /** Badge text: work-day position for a lump-sum item, lifecycle otherwise. */
  badge: string;
  badgeVariant: BadgeVariant;
  /**
   * Secondary line beside "Started <date>". The calendar deadline for a
   * non-lump-sum item; for a lump-sum one, the spent-allowance summary, and
   * empty while the allowance still holds (the badge already says "Day N of M"
   * and the frozen due date would only confuse).
   */
  meta: string;
}

// Human labels + badge tone for a NON-lump-sum work item's calendar lifecycle.
// Kept here rather than imported from the editor so this module stays pure.
const CALENDAR_LABEL: Record<string, string> = {
  IN_PROGRESS: "In progress",
  DUE_TODAY: "Due today",
  OVERDUE: "Overdue",
  COMPLETED_ON_TIME: "Completed",
  COMPLETED_LATE: "Completed late",
};
const CALENDAR_VARIANT: Record<string, BadgeVariant> = {
  IN_PROGRESS: "neutral",
  DUE_TODAY: "warning",
  OVERDUE: "danger",
  COMPLETED_ON_TIME: "success",
  COMPLETED_LATE: "warning",
};

/** Whether this row is measured in work days. Older backends omit the flag; a
 * missing value means "not lump-sum", which falls back to the calendar
 * presentation the card has always had. */
export function isLumpsumTask(task: Pick<OpenTask, "is_lumpsum">): boolean {
  return task.is_lumpsum === true;
}

/** Work days a lump-sum item is allowed, clamped exactly as the backend clamps
 * it: a blank/zero benchmark period still grants one work day. */
export function allowedWorkDays(targetDays: number): number {
  return Math.max(1, targetDays);
}

/** Work days already spent, before the report being written. */
export function usedWorkDays(task: Pick<OpenTask, "days_used">): number {
  return Math.max(0, task.days_used ?? 0);
}

/** True once every allowed work day has been spent, so the next one needs
 * Project Head approval. Mirrors lumpsum_allowance_exhausted. */
export function allowanceExhausted(usedDays: number, targetDays: number): boolean {
  return usedDays >= allowedWorkDays(targetDays);
}

/** "Day 2 of 3" — where the report being written sits in the allowance. Only
 * meaningful while the allowance holds. */
export function workDayPositionLabel(usedDays: number, targetDays: number): string {
  return `Day ${usedDays + 1} of ${allowedWorkDays(targetDays)}`;
}

/** "Used 2 of 2 allowed work days", and once approved continuation days have
 * been worked, "Used 4 work days - 2 allowed" (never "4 of 2"). */
export function workDaysSpentLabel(usedDays: number, targetDays: number): string {
  const allowed = allowedWorkDays(targetDays);
  if (usedDays > allowed) {
    return `Used ${usedDays} work days - ${allowed} allowed`;
  }
  return `Used ${usedDays} of ${allowed} allowed work ${allowed === 1 ? "day" : "days"}`;
}

/** Everything the Open Task card needs to render, for either kind of item. */
export function openTaskCardState(task: OpenTask): OpenTaskCardState {
  if (isLumpsumTask(task)) {
    const used = usedWorkDays(task);
    const allowed = allowedWorkDays(task.target_days);
    if (allowanceExhausted(used, task.target_days)) {
      return {
        badge: "Duration exceeded",
        badgeVariant: "danger",
        meta: workDaysSpentLabel(used, task.target_days),
      };
    }
    return {
      badge: workDayPositionLabel(used, task.target_days),
      // The last allowed work day is worth flagging; earlier ones are not.
      badgeVariant: used === allowed - 1 ? "warning" : "neutral",
      meta: "",
    };
  }

  // Non-lump-sum: the calendar due date is still the rule, so keep saying it.
  const overdueDays = task.days_overdue ?? 0;
  return {
    badge:
      task.lifecycle === "OVERDUE" && overdueDays > 0
        ? `Overdue ${overdueDays}d`
        : CALENDAR_LABEL[task.lifecycle] ?? task.lifecycle,
    badgeVariant: CALENDAR_VARIANT[task.lifecycle] ?? "neutral",
    meta: `Due ${task.due_date}`,
  };
}

/**
 * The "Overall task" badge on a SAVED report row (Report Detail), which is the
 * same question the Open Task card asks about the same work item — how much of
 * the allowed duration is spent — so it is answered by the same helpers rather
 * than by a second rule.
 *
 * The row is measured by whatever governs its item:
 *   * lump-sum, still open -> WORK DAYS. `overall_days_used` counts the days
 *     spent BEFORE this report (backend work_items.days_used_before, the same
 *     convention as OpenTask.days_used), so this report is day used + 1:
 *     "Day 1 of 2", "Day 2 of 2", then "Duration exceeded" once the allowance
 *     is spent and continuing needs Project Head approval.
 *   * anything else -> the CALENDAR lifecycle it has always had, including
 *     "Overdue by Nd" from the frozen due date.
 *
 * Completion is a calendar verdict for BOTH kinds (the backend sends
 * COMPLETED_ON_TIME / COMPLETED_LATE and no work-day fields), so a completed
 * row falls through to the calendar branch by construction.
 *
 * Returns null when the server sent no lifecycle at all — a legacy standalone
 * row, which the caller renders its own way.
 */
export interface OverallTaskBadge {
  text: string;
  variant: BadgeVariant;
}

export interface OverallTaskRow {
  overall_lifecycle?: string | null;
  overall_is_lumpsum?: boolean | null;
  overall_target_days?: number | null;
  overall_days_used?: number | null;
  days_overdue?: number | null;
}

export function overallTaskBadge(row: OverallTaskRow): OverallTaskBadge | null {
  const lifecycle = row.overall_lifecycle;
  if (!lifecycle) return null;

  if (row.overall_is_lumpsum === true && row.overall_days_used != null) {
    const target = row.overall_target_days ?? 1;
    const used = Math.max(0, row.overall_days_used);
    const allowed = allowedWorkDays(target);
    if (allowanceExhausted(used, target)) {
      return { text: "Duration exceeded", variant: "danger" };
    }
    return {
      text: workDayPositionLabel(used, target),
      // The last allowed work day is worth flagging; earlier ones are not.
      variant: used === allowed - 1 ? "warning" : "neutral",
    };
  }

  const overdueDays = row.days_overdue ?? 0;
  return {
    text:
      lifecycle === "OVERDUE" && overdueDays > 0
        ? `Overdue by ${overdueDays}d`
        : CALENDAR_LABEL[lifecycle] ?? lifecycle,
    variant: CALENDAR_VARIANT[lifecycle] ?? "neutral",
  };
}

/**
 * Continuation-approval state of ONE editor row. It is a LABEL, not a gate: it
 * decides what the row says about itself and nothing else. A pending
 * continuation does not disable the completion checkbox, and never blocked
 * saving or submitting - the Project Head's decision settles whether that
 * continuation work is ultimately accepted, not whether the employee may fill
 * in and finish the report describing it. (The backend agrees: work_items
 * _apply_completion / complete_via_endpoint both complete normally while a
 * request is pending, and a rejection later withdraws the day's rows and the
 * completion stamped on them.)
 *
 * A row can learn its state from two places and they must agree: a SAVED row
 * carries `continuation_approval_status` from the API, while a row the employee
 * has just attached to an open work item has nothing saved yet - its state is
 * whatever the open item says will happen when the report is saved. Deriving it
 * once, here, is what keeps the editor from inventing a second rule.
 *
 * `null` means no approval is involved: not a lump-sum activity, or one still
 * inside its allowed work days.
 */
export type ContinuationStatus = "pending" | "approved" | "rejected" | null;

export function continuationRowStatus(
  savedStatus: ContinuationStatus | undefined,
  openTask?: OpenTask | null,
): ContinuationStatus {
  if (savedStatus) return savedStatus;
  if (!openTask || !isLumpsumTask(openTask)) return null;
  if (!allowanceExhausted(usedWorkDays(openTask), openTask.target_days)) return null;
  // Past the allowance with no request yet: saving this row raises one, so the
  // row is about to be pending and should say so before the employee submits.
  return (openTask.continuation_status as ContinuationStatus) ?? "pending";
}

/**
 * The whole of what a PENDING continuation says on a row - two short lines and
 * no more. Kept here rather than inline in ContinuationRowStatus so the copy is
 * a pure value the unit tests can pin, and so the compact (editor) and full
 * (report detail) presentations cannot drift apart.
 *
 * Deliberately says nothing about being blocked, because nothing is: earlier
 * copy explained that the entry was not recorded work yet, that completion was
 * held, that the report could still be submitted and that a rejection would
 * remove the entry. That is four caveats on a row whose only fact is that a
 * decision is outstanding.
 */
export const CONTINUATION_PENDING_TITLE = "Continuation requested";
export const CONTINUATION_PENDING_DETAIL = "Awaiting Project Head approval.";

/** The parenthetical in the inline "You have an open task for this activity"
 * prompt, which offers Continue-existing vs Start-new on a manual pick. Same
 * split: a calendar deadline only where a calendar deadline still decides
 * something. */
export function openTaskInlineSummary(task: OpenTask): string {
  if (isLumpsumTask(task)) {
    const used = usedWorkDays(task);
    return allowanceExhausted(used, task.target_days)
      ? `started ${task.started_on}, ${workDaysSpentLabel(used, task.target_days).toLowerCase()}`
      : `started ${task.started_on}, ${workDayPositionLabel(used, task.target_days).toLowerCase()}`;
  }
  return `started ${task.started_on}, due ${task.due_date}`;
}
