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
 * An ISO instant as an Asia/Kolkata wall-clock string.
 *
 * Punch times are stored as timezone-aware UTC, and attendance-day semantics
 * are IST everywhere in this product, so the zone is pinned rather than left to
 * whatever the viewing machine is set to. A PM checking a punch window against
 * the EasyTime console must see the same digits the console shows.
 */
export function formatIST(iso: string | null | undefined): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "-";
  return d.toLocaleString("en-GB", {
    timeZone: "Asia/Kolkata",
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/**
 * Time part only, `HH:MM` on the 24-hour IST clock - for calendar cells.
 *
 * Returns EMPTY_TIME rather than "-" for a missing value so a first-in/last-out
 * pair stays column-aligned in a dense month grid, and so a missing OUT reads as
 * "not recorded" instead of looking like a formatting failure.
 */
export const EMPTY_TIME = "--:--";

export function formatISTTime(iso: string | null | undefined): string {
  if (!iso) return EMPTY_TIME;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return EMPTY_TIME;
  return d.toLocaleTimeString("en-GB", {
    timeZone: "Asia/Kolkata",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
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
