import { api } from "@/lib/api-client";
import { getToken } from "@/lib/auth-storage";
import { env } from "@/lib/env";

import type {
  ActivityOption,
  ActivityReport,
  ActivityReportFilters,
  SubActivityOption,
} from "./types";

function toQuery(f: ActivityReportFilters): string {
  const sp = new URLSearchParams();
  if (f.employee_id) sp.set("employee_id", f.employee_id);
  if (f.project_id) sp.set("project_id", f.project_id);
  if (f.activity_id) sp.set("activity_id", f.activity_id);
  if (f.sub_activity_id) sp.set("sub_activity_id", f.sub_activity_id);
  if (f.from) sp.set("from", f.from);
  if (f.to) sp.set("to", f.to);
  return sp.toString();
}

export const reportsExportApi = {
  rows: (f: ActivityReportFilters) =>
    api.get<ActivityReport>(`/reports-export/activity-rows?${toQuery(f)}`),
  activities: () => api.get<ActivityOption[]>("/activity-master/activities"),
  subActivities: () => api.get<SubActivityOption[]>("/activity-master/sub-activities"),
};

/**
 * Streams the styled .xlsx (same filters as the preview) and triggers a browser
 * download. Goes through fetch directly (not api-client) because the response is
 * a binary blob, not JSON — but still attaches the bearer token.
 */
export async function downloadActivityXlsx(f: ActivityReportFilters): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}/reports-export/activity-rows.xlsx?${toQuery(f)}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "weekly-activity-report.xlsx";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
