/**
 * Status + detail line for one TASK_BASED row of the employee dashboard's
 * "Benchmark Activities" card. Pure (today is passed in) so the component stays
 * a renderer.
 *
 * The two kinds of row are measured by different clocks, exactly as they are on
 * the Open Task card and the Report Detail "Overall task" badge:
 *
 *   * LUMP-SUM  -> WORK DAYS. `days_used` is the work days spent BEFORE today,
 *     so today is day days_used + 1 and the row reads "Day 2 of 2" while the
 *     allowance holds. Overdue means the allowance is spent and the next work
 *     day needs Project Head approval - never merely that a frozen calendar
 *     due_date has passed. Skipped calendar days consume nothing, so they can't
 *     make the row overdue.
 *   * everything else -> the CALENDAR due date it has always used: "Due in N
 *     Days" / "Due Today" / "N Days Overdue".
 *
 * The work-day arithmetic is not re-derived here: allowanceExhausted /
 * workDayPositionLabel / workDaysSpentLabel are the same helpers the work-report
 * surfaces use, which in turn mirror backend work_items.lumpsum_* one for one.
 */
import {
  allowanceExhausted,
  workDayPositionLabel,
  workDaysSpentLabel,
} from "../work-reports/open-task-state.ts";

import type { TaskStatusRow } from "./types.ts";

export type BenchmarkTaskStatus = "in_progress" | "overdue";

export interface BenchmarkTaskState {
  status: BenchmarkTaskStatus;
  detail: string;
}

/** Whole-day difference between a due date and today. >0 future, 0 today, <0 past. */
function dueDayDiff(due: string, today: Date): number {
  const [y, m, d] = due.split("-").map(Number);
  return Math.round((new Date(y, m - 1, d).getTime() - today.getTime()) / 86_400_000);
}

export function benchmarkTaskState(row: TaskStatusRow, today: Date): BenchmarkTaskState {
  if (row.is_lumpsum === true && row.days_used != null) {
    const target = row.target_days ?? 1;
    const used = Math.max(0, row.days_used);
    return allowanceExhausted(used, target)
      ? { status: "overdue", detail: workDaysSpentLabel(used, target) }
      : { status: "in_progress", detail: workDayPositionLabel(used, target) };
  }

  const diff = dueDayDiff(row.due_date, today);
  if (diff > 0) {
    return {
      status: "in_progress",
      detail: diff === 1 ? "Due in 1 Day" : `Due in ${diff} Days`,
    };
  }
  if (diff === 0) return { status: "in_progress", detail: "Due Today" };
  const n = -diff;
  return { status: "overdue", detail: n === 1 ? "1 Day Overdue" : `${n} Days Overdue` };
}
