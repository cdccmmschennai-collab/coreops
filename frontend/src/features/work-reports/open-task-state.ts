/**
 * How one Open Task card presents itself — pure, no React.
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
