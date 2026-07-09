// Shared date/format helpers for the dashboards. All "today"/"this week" logic
// is anchored to IST (see @/lib/ist) — the office runs on Asia/Kolkata.

import { istTodayISO, nowInIST } from "@/lib/ist";

export function todayISO(): string {
  return istTodayISO();
}

/**
 * Start of the current benchmark cycle (Friday) in IST. The cycle runs
 * Fri..Thu, mirroring the backend's compute_week_bounds — keep the two in
 * lockstep or the dashboard label/date filters drift from the ledger data.
 */
export function weekStartISO(): string {
  const now = nowInIST();
  const fri = new Date(now);
  fri.setDate(now.getDate() - ((now.getDay() + 2) % 7)); // days since Friday
  const y = fri.getFullYear();
  const m = String(fri.getMonth() + 1).padStart(2, "0");
  const d = String(fri.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function greeting(): string {
  const h = nowInIST().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

/** True when an ISO timestamp falls on the current IST calendar day. */
export function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = nowInIST();
  return (
    d.getFullYear() === now.getFullYear() &&
    d.getMonth() === now.getMonth() &&
    d.getDate() === now.getDate()
  );
}

/** Compact "20 mins ago" relative time from an ISO timestamp. */
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min${mins > 1 ? "s" : ""} ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} hour${hrs > 1 ? "s" : ""} ago`;
  const days = Math.floor(hrs / 24);
  return `${days} day${days > 1 ? "s" : ""} ago`;
}
