// Small date helpers for the attendance calendar (local time, no deps).

export const MONTHS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const pad = (n: number) => String(n).padStart(2, "0");

/** ISO yyyy-mm-dd for a Y/M(0-indexed)/D. */
export function isoDate(y: number, m: number, d: number): string {
  return `${y}-${pad(m + 1)}-${pad(d)}`;
}

/** First and last day of a month as ISO strings (m is 0-indexed). */
export function monthRange(y: number, m: number): { from: string; to: string } {
  const last = new Date(y, m + 1, 0).getDate();
  return { from: isoDate(y, m, 1), to: isoDate(y, m, last) };
}

/** Days in a month (m 0-indexed). */
export function daysInMonth(y: number, m: number): number {
  return new Date(y, m + 1, 0).getDate();
}

/** Day-of-week of the 1st with Monday=0 … Sunday=6. */
export function firstDowMonday(y: number, m: number): number {
  return (new Date(y, m, 1).getDay() + 6) % 7;
}

/** Which occurrence of its weekday a date is within the month (day 1–7 → 1st,
 * 8–14 → 2nd, …). Works for Saturdays since they fall 7 days apart. */
function weekdayOccurrence(d: number): number {
  return Math.floor((d - 1) / 7) + 1;
}

/** True if the given Y/M/D is a non-working (off) day under the office calendar.
 * Sundays are always off; Saturdays are off only on the 2nd and 4th of the
 * month — the 1st, 3rd and 5th Saturdays are working office days. */
export function isWeekend(y: number, m: number, d: number): boolean {
  const dow = new Date(y, m, d).getDay();
  if (dow === 0) return true; // Sunday — always off
  if (dow === 6) {
    const nth = weekdayOccurrence(d);
    return nth === 2 || nth === 4; // 2nd & 4th Saturday off; 1st/3rd/5th working
  }
  return false;
}

export function prevMonth(y: number, m: number): { y: number; m: number } {
  return m === 0 ? { y: y - 1, m: 11 } : { y, m: m - 1 };
}

export function nextMonth(y: number, m: number): { y: number; m: number } {
  return m === 11 ? { y: y + 1, m: 0 } : { y, m: m + 1 };
}
