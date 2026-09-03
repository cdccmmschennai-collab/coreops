/**
 * The Attendance page's tab configuration. Pure, import-free.
 *
 * No imports and no `@/` alias, so the host-Node unit test can load this file
 * directly - the repo has no DOM/component test harness, so the way a label is
 * made testable is to keep it out of the component.
 *
 * The KEY and the LABEL are deliberately separate concerns:
 *   - `value` is a URL token (`/attendance?tab=history`). It is part of the
 *     addressable surface: bookmarks, the PM dashboard's `?tab=leave` shortcut
 *     and `useUrlState` all depend on it, so renaming one silently breaks links
 *     that already exist in the wild.
 *   - `label` is display text and may be reworded freely.
 * `history` therefore keeps its key while reading "Records" - see attendanceTabs.
 */

export type TabKey =
  | "calendar"
  | "history"
  | "leave"
  | "leave-balance"
  | "corrections"
  | "holidays";

export interface TabItem {
  value: TabKey;
  label: string;
}

export interface TabOptions {
  /** `attendance.manage` - gates the Leave Balance maintenance view. */
  canManage: boolean;
  /** `features.attendanceCorrections`, deferred until automated capture exists. */
  correctionsEnabled: boolean;
}

/**
 * The tabs to render, in display order.
 *
 * "Records" (key `history`) is the PM's DAILY REVIEW: one date, every in-scope
 * employee, their biometric evidence and whether the day is settled. It is a
 * review surface, not the attendance ledger - nothing on it is approved or
 * written. Manager-only, because it shows the whole roster.
 */
export function attendanceTabs({ canManage, correctionsEnabled }: TabOptions): TabItem[] {
  return [
    { value: "calendar", label: "Calendar" },
    // Records is the PM's daily review of the whole roster, so it is
    // manager-only: an employee has no business reading everyone else's day.
    // Their own attendance lives on the Calendar tab.
    ...(canManage ? ([{ value: "history", label: "Records" }] as TabItem[]) : []),
    // Label only - the `leave` KEY is the URL parameter every leave deep-link,
    // notification and dashboard shortcut names, so it never changes with the
    // wording (the same reason `history` still reads "Records").
    { value: "leave", label: "Leave Requests" },
    // Leave Balance is a manager/admin-only maintenance view.
    ...(canManage ? ([{ value: "leave-balance", label: "Leave Balance" }] as TabItem[]) : []),
    // Corrections is deferred until biometric / automated attendance capture
    // exists (attendance is entered manually today). Hidden behind a feature
    // flag; see features.attendanceCorrections.
    ...(correctionsEnabled ? ([{ value: "corrections", label: "Corrections" }] as TabItem[]) : []),
    { value: "holidays", label: "Holidays" },
  ];
}

/**
 * The tab a URL may select, given the same options.
 *
 * Derived from `attendanceTabs` rather than listed a second time: a tab that is
 * not rendered must not be reachable by typing its key into the URL, and two
 * hand-maintained lists would eventually disagree about that.
 */
export function allowedTabKeys(options: TabOptions): TabKey[] {
  return attendanceTabs(options).map((t) => t.value);
}

/**
 * A raw `?tab=` value as a tab that actually exists for this user.
 *
 * Anything else - a stale URL, a typo, or a manager-only tab requested by a
 * non-manager - falls back to Calendar rather than rendering nothing.
 */
export function resolveTab(raw: string, options: TabOptions): TabKey {
  return (allowedTabKeys(options) as string[]).includes(raw) ? (raw as TabKey) : "calendar";
}
