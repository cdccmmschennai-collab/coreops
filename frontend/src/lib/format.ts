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

/** Format an ISO datetime as a short local "HH:MM" (or "—" when missing). */
export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
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
