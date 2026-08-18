/**
 * Pure presentation helpers for the biometric mapping screen.
 *
 * No imports, no React, no `@/` alias - the host-Node unit test loads this file
 * directly. Everything here is display-only: none of it decides a mapping.
 */

/** "EMP061 - Asha Rao". The one format the employee selector ever shows, so a
 *  PM always confirms against the code AND the name, never a name alone. */
export function employeeLabel(
  code: string | null | undefined,
  name: string | null | undefined,
): string {
  const parts = [code, name].filter((p): p is string => Boolean(p && p.trim()));
  return parts.length ? parts.join(" - ") : "-";
}

/**
 * The IST wall-clock hour and minute of an ISO instant.
 *
 * Punch times are stored as timezone-aware UTC and attendance-day semantics are
 * IST everywhere in this product, so the zone is PINNED rather than left to
 * whatever the viewing machine is set to. The conversion is done by Intl (which
 * knows the offset) and only the RENDERING is done by hand below - reading the
 * digits out of the ISO string instead would show a Chennai punch in UTC.
 */
function istHourMinute(d: Date): { hour: number; minute: number } | null {
  // en-GB + hour12:false gives "13:00" - stable across engines, unlike the
  // locale's own 12-hour output, which varies in case ("pm" vs "PM") and in
  // whether it pads the hour.
  const text = d.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const m = /^(\d{1,2}):(\d{2})/.exec(text);
  if (!m) return null;
  // Some ICU versions render midnight as "24:00" in this locale.
  return { hour: Number(m[1]) % 24, minute: Number(m[2]) };
}

/**
 * A 24-hour clock reading as the 12-hour one CoreOps displays: `13:00` ->
 * `"01:00 PM"`.
 *
 * The company reads times on a 12-hour clock, so "railway time" was removed
 * from every attendance surface on 2026-08-18. This matches `lib/format.ts`'s
 * `to12Hour` byte for byte - the same shape the leave, permission and project
 * screens already use - so one time never reads differently from another. Do
 * not reintroduce a 24-hour attendance display.
 */
export function to12Hour(hour: number, minute: number): string {
  const period = hour < 12 ? "AM" : "PM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${String(h12).padStart(2, "0")}:${String(minute).padStart(2, "0")} ${period}`;
}

/** An ISO instant as an IST date + 12-hour time: `"29 Jul 2026, 10:12 AM"`. */
export function formatIST(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  const date = d.toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
  const parts = istHourMinute(d);
  return parts ? `${date}, ${to12Hour(parts.hour, parts.minute)}` : date;
}

/**
 * Time part only, `hh:MM AM/PM` on the IST clock - for calendar cells.
 *
 * Returns EMPTY_TIME rather than "-" for a missing value so a first-in/last-out
 * pair stays column-aligned in a dense month grid, and so a missing OUT reads as
 * "not recorded" instead of looking like a formatting failure.
 */
export const EMPTY_TIME = "--:-- --";

export function formatISTTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY_TIME;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EMPTY_TIME;
  const parts = istHourMinute(d);
  return parts ? to12Hour(parts.hour, parts.minute) : EMPTY_TIME;
}

/**
 * The IST clock reading as `HH:MM` on the 24-hour clock - a MACHINE value, not
 * a display one.
 *
 * `<input type="time">` accepts only 24-hour `HH:MM`; handing it "05:30 PM"
 * silently blanks the field. So the PM decision dialog prefills from this while
 * every visible time goes through `formatISTTime`. Returns "" when there is no
 * usable value, which is what an empty input expects.
 */
export function istTimeInputValue(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const parts = istHourMinute(d);
  if (!parts) return "";
  return `${String(parts.hour).padStart(2, "0")}:${String(parts.minute).padStart(2, "0")}`;
}

/** Date part only, for the compact first-seen/last-seen columns. */
export function formatISTDate(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleDateString("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}
