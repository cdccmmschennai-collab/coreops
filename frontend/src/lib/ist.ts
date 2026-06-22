/**
 * India Standard Time helpers.
 *
 * This product serves a single office (Chennai), so all *functional* time-of-day
 * and "today" logic is anchored to Asia/Kolkata (UTC+5:30, no DST) regardless of
 * the timezone configured on the user's machine. Use these instead of a bare
 * `new Date()` whenever the value drives a decision (today's date, the report
 * reminder hour, the current week), not just display.
 */
export const IST_TIME_ZONE = "Asia/Kolkata";

/**
 * A Date whose *local* getters (getHours, getDate, getFullYear, …) read out the
 * current IST wall-clock time. Asia/Kolkata has no DST, so this is exact.
 */
export function nowInIST(): Date {
  return new Date(new Date().toLocaleString("en-US", { timeZone: IST_TIME_ZONE }));
}

/** Today's date in IST as an ISO `YYYY-MM-DD` string. */
export function istTodayISO(): string {
  const d = nowInIST();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
