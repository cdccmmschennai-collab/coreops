/**
 * Submission-reminder presentation logic (PM dashboard, Phase 3).
 *
 * Pure and framework-free so it runs under `node --test`. It ONLY filters,
 * orders, caps and labels what the backend already decided:
 * `deadline_state` and `days_remaining` are computed server-side in IST
 * (ADR-003 Amendment 2). Nothing here reads the browser's clock.
 *
 * Imports are type-only so this file stays runnable by node's type stripping.
 */
import type { DeadlineState, Deliverable } from "./types";

/** Reminder priority: lower sorts first. Completed is not a reminder at all. */
export const STATE_PRIORITY: Record<DeadlineState, number> = {
  overdue: 0,
  due_today: 1,
  urgent: 2,
  due_soon: 3,
  on_track: 4,
  no_deadline: 5,
  completed: 6,
};

export const DEADLINE_STATE_LABEL: Record<DeadlineState, string> = {
  overdue: "Overdue",
  due_today: "Due today",
  urgent: "Urgent",
  due_soon: "Upcoming",
  on_track: "On track",
  no_deadline: "No deadline",
  completed: "Completed",
};

type ReminderFields = Pick<
  Deliverable,
  "id" | "name" | "target_date" | "deadline_state" | "days_remaining"
>;

export function isPending(d: Pick<Deliverable, "deadline_state">): boolean {
  return d.deadline_state !== "completed";
}

/**
 * Priority order: overdue, due today, 1 day, 2-5 days, later, no deadline.
 * Within a group, earliest deadline first (no-date last), then name for a
 * stable order. Returns a new array.
 */
export function sortReminders<T extends ReminderFields>(items: readonly T[]): T[] {
  return [...items].sort((a, b) => {
    const byState = STATE_PRIORITY[a.deadline_state] - STATE_PRIORITY[b.deadline_state];
    if (byState !== 0) return byState;
    const ad = a.target_date ?? "9999-12-31";
    const bd = b.target_date ?? "9999-12-31";
    if (ad !== bd) return ad < bd ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export interface ReminderRows<T> {
  /** Pending reminders to render, in priority order, at most `max`. */
  rows: T[];
  /** Pending reminders beyond `max` (the "+N more pending" count). */
  hidden: number;
}

/**
 * One flat, priority-ordered list of pending (non-completed) reminders,
 * capped at `max` rows. Priority is conveyed by order and badge only - there
 * are no group headings.
 */
export function selectReminderRows<T extends ReminderFields>(
  items: readonly T[],
  max: number,
): ReminderRows<T> {
  const sorted = sortReminders(items.filter(isPending));
  const rows = sorted.slice(0, Math.max(0, max));
  return { rows, hidden: sorted.length - rows.length };
}

/**
 * Whose login banner a deliverable belongs on: its Assignee, plus whoever
 * manages it (the project's Head, or a PM) - the backend's per-row
 * `can_manage`. Other project members do not get reminders for deliverables
 * that are not theirs.
 */
export function isMyDeliverable(
  d: { owner_employee_id: string | null; can_manage: boolean },
  employeeId: string | null | undefined,
): boolean {
  return d.can_manage || (!!employeeId && d.owner_employee_id === employeeId);
}

/** Login banner window: planned deliverables due within this many days. */
export const LOGIN_REMINDER_DAYS = 3;

/**
 * Deliverables for the login banner (Head + project members): still planned
 * and due today up to `windowDays` days ahead, earliest first. Overdue and
 * undated rows are not included. Uses the backend's `days_remaining` only.
 */
export function selectLoginReminders<T extends ReminderFields>(
  items: readonly T[],
  windowDays: number = LOGIN_REMINDER_DAYS,
): T[] {
  return sortReminders(
    items.filter(
      (d) =>
        d.deadline_state !== "completed" &&
        d.days_remaining !== null &&
        d.days_remaining >= 0 &&
        d.days_remaining <= windowDays,
    ),
  );
}

/** "Due today" / "Due tomorrow" / "Due in 3 days" for the login banner. */
export function dueInLabel(daysRemaining: number): string {
  if (daysRemaining <= 0) return "Due today";
  if (daysRemaining === 1) return "Due tomorrow";
  return `Due in ${daysRemaining} days`;
}

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/** Human countdown from the backend's signed `days_remaining`. */
export function daysRemainingLabel(
  d: Pick<Deliverable, "deadline_state" | "days_remaining">,
): string {
  if (d.deadline_state === "completed") return "Completed";
  const n = d.days_remaining;
  if (n === null) return "No deadline set";
  if (n < 0) return `${plural(-n, "day")} overdue`;
  if (n === 0) return "Due today";
  return `${plural(n, "day")} remaining`;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/**
 * "2026-11-14" -> "14 Nov 2026". Splits the ISO date string instead of going
 * through `Date`, so no timezone can shift the displayed day.
 */
export function formatDueDate(iso: string | null): string {
  if (!iso) return "No deadline";
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return iso;
  const month = MONTHS[Number(m[2]) - 1];
  return month ? `${Number(m[3])} ${month} ${m[1]}` : iso;
}

/** Exact detail-page route for one deliverable (shared with notifications). */
export function deliverableHref(id: string): string {
  return `/projects/deliverables/${id}`;
}
