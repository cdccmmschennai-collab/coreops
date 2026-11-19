/**
 * Where "← Reports" on a report page goes.
 *
 * Opened from an in-app list (the Reports log, a dashboard, an employee's
 * Reports tab, a rework request), Back steps back to that list so its filters
 * survive. Opened from anywhere else - a notification, an email link, a pasted
 * URL - Back goes to the Reports log instead of returning to where the link
 * was clicked.
 *
 * A URL flag can't carry this: the preview -> Edit -> Save round trip REPLACES
 * the address (see history-nav.test.ts), which would drop it. Session storage
 * survives that round trip and is per-tab. Every access is guarded - storage
 * can be unavailable (private mode, blocked site data), which simply means the
 * Reports-log fallback.
 */

const KEY = "coreops:report-opened-from-list";

/** Call when an in-app list opens report `reportId`. */
export function markReportOpenedFromList(reportId: string): void {
  try {
    window.sessionStorage.setItem(KEY, reportId);
  } catch {
    /* storage unavailable - Back falls back to the Reports log */
  }
}

/** Call when something OUTSIDE a list (a notification) opens a page. */
export function clearReportOpenedFromList(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}

export function wasReportOpenedFromList(reportId: string): boolean {
  try {
    return window.sessionStorage.getItem(KEY) === reportId;
  } catch {
    return false;
  }
}
