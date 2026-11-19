/**
 * Rework Approval presentation helpers. Pure, so `node --test` can pin them.
 */
import type { ReworkFilters, ReworkStatus } from "./types";

export const PAGE_SIZE = 10;

export const STATUS_LABEL: Record<ReworkStatus, string> = {
  pending: "Pending",
  approved: "Approved",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

export const STATUS_TONE: Record<ReworkStatus, "warning" | "success" | "danger" | "neutral"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  cancelled: "neutral",
};

const DAY_PART_LABEL: Record<string, string> = {
  full_day: "Full Day",
  first_half: "First Half",
  second_half: "Second Half",
};

export function dayPartLabel(part: string | null | undefined): string {
  return part ? DAY_PART_LABEL[part] ?? part : "-";
}

/** "CDC031 - ABIRAMI S" - the same shape as the outstanding-report email. */
export function employeeLabel(code: string | null | undefined, name: string): string {
  return code ? `${code} - ${name}` : name;
}

/** Query string for GET /rework-approvals. Empty filters are omitted. */
export function buildListQuery(f: ReworkFilters): string {
  const params = new URLSearchParams();
  for (const key of ["status", "project_id", "employee_id", "report_date", "sub_activity_id"] as const) {
    const value = f[key].trim();
    if (value) params.set(key, value);
  }
  params.set("limit", String(PAGE_SIZE));
  params.set("offset", String(Math.max(0, f.offset)));
  return params.toString();
}

export function hasActiveFilters(f: ReworkFilters): boolean {
  return [f.status, f.project_id, f.employee_id, f.report_date, f.sub_activity_id].some(
    (v) => v.trim() !== "",
  );
}

/** Rejection needs a non-blank reason; approval remarks are optional. */
export function canSubmitDecision(kind: "approve" | "reject", remarks: string): boolean {
  return kind === "approve" || remarks.trim().length > 0;
}
