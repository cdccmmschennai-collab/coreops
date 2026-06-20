/** Format a numeric/decimal-string value (e.g. benchmark counts, which the API
 * may return as Decimal-backed strings/floats like "250.00") as a whole
 * number for display — "250.00" → "250". Falls back to "—" when missing. */
export function formatInt(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = Math.round(Number(value));
  return Number.isFinite(n) ? String(n) : "—";
}

/** Format a whole-minute duration as "Xh Ym" (e.g. 540 → "9h 0m"). */
export function formatMinutes(minutes: number): string {
  const safe = Math.max(0, Math.trunc(minutes));
  const h = Math.floor(safe / 60);
  const m = safe % 60;
  return `${h}h ${m}m`;
}

/** Pull the literal wall-clock parts out of an ISO datetime WITHOUT any
 * timezone conversion. CoreOps operates entirely in IST: times are entered and
 * stored as the wall-clock the user typed, so we echo those exact digits rather
 * than letting the browser/server timezone shift them (which is what
 * `Date.toLocale*` does). */
function parseWallClock(
  iso: string,
): { year: number; month: number; day: number; hour: number; minute: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso);
  if (!m) return null;
  return {
    year: Number(m[1]),
    month: Number(m[2]),
    day: Number(m[3]),
    hour: Number(m[4]),
    minute: Number(m[5]),
  };
}

/** Render a 24h hour/minute as a 12h "hh:MM AM/PM" clock string. */
function to12Hour(hour: number, minute: number): string {
  const period = hour < 12 ? "AM" : "PM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${String(h12).padStart(2, "0")}:${String(minute).padStart(2, "0")} ${period}`;
}

/** Format an ISO datetime as a 12h IST wall-clock "hh:MM AM/PM" (or "—"). */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const wc = parseWallClock(iso);
  if (!wc) return "—";
  return to12Hour(wc.hour, wc.minute);
}

/** Format an ISO datetime as a short local "MMM D, YYYY, HH:MM" (or "—" when missing). */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** ISO datetime → value for <input type="datetime-local"> ("YYYY-MM-DDTHH:MM"). */
export function toDatetimeLocal(iso: string | null | undefined): string {
  if (!iso) return "";
  // Keep the date+time portion; the API returns timezone-aware ISO strings.
  return iso.slice(0, 16);
}
