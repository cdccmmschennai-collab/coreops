import { api } from "@/lib/api-client";
import { getToken } from "@/lib/auth-storage";
import { env } from "@/lib/env";

import {
  weeklyReportExportPath,
  weeklyReportPath,
  type WeeklyReportCycle,
} from "./weekly-report";

import type {
  ActivityMember,
  ActivityMemberCreateBody,
  ActivityMemberUpdateBody,
  ActivityStaffing,
  AssignableEmployee,
  PlannedDateChange,
  PlannedDateUpdateBody,
  Project,
  ProjectCreateBody,
  ProjectHeadUpdateBody,
  ProjectListParams,
  ProjectMember,
  ProjectMemberCreateBody,
  ProjectMemberRole,
  ProjectPage,
  ProjectSummary,
  ProjectTimelineEvent,
  ProjectUpdateBody,
  TagScope,
  TagScopeUpdateBody,
  WeeklyReport,
} from "./types";

function toQuery(p: ProjectListParams): string {
  const sp = new URLSearchParams();
  if (p.q) sp.set("q", p.q);
  if (p.status) sp.set("status", p.status);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const projectsApi = {
  list: (params: ProjectListParams) =>
    api.get<ProjectPage>(`/projects?${toQuery(params)}`),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  create: (body: ProjectCreateBody) => api.post<Project>("/projects", body),
  update: (id: string, body: ProjectUpdateBody) =>
    api.patch<Project>(`/projects/${id}`, body),
  archive: (id: string) => api.del<void>(`/projects/${id}`),

  setHead: (id: string, body: ProjectHeadUpdateBody) =>
    api.put<Project>(`/projects/${id}/head`, body),

  // Tag scope. Both verbs return the same payload (current scope + full
  // history), so a successful write refreshes the whole tab in one round trip.
  getTagScope: (id: string) => api.get<TagScope>(`/projects/${id}/tag-scope`),
  updateTagScope: (id: string, body: TagScopeUpdateBody) =>
    api.put<TagScope>(`/projects/${id}/tag-scope`, body),
  getSummary: (id: string) => api.get<ProjectSummary>(`/projects/${id}/summary`),

  // Weekly Report preview. Head-only server-side, so the caller gates the
  // query on the same authority rather than firing a guaranteed 403. The path
  // is built by the shared helper the download also uses, so the two can never
  // ask for different weeks.
  getWeeklyReport: (id: string, cycle: WeeklyReportCycle) =>
    api.get<WeeklyReport>(weeklyReportPath(id, cycle)),

  updatePlannedDate: (id: string, body: PlannedDateUpdateBody) =>
    api.patch<Project>(`/projects/${id}/planned-completion-date`, body),
  listPlannedDateChanges: (id: string) =>
    api.get<PlannedDateChange[]>(`/projects/${id}/planned-date-changes`),
  listTimeline: (id: string) =>
    api.get<ProjectTimelineEvent[]>(`/projects/${id}/timeline`),

  listMembers: (id: string) => api.get<ProjectMember[]>(`/projects/${id}/members`),
  addMember: (id: string, body: ProjectMemberCreateBody) =>
    api.post<ProjectMember>(`/projects/${id}/members`, body),
  updateMemberRole: (id: string, employeeId: string, role: ProjectMemberRole) =>
    api.patch<ProjectMember>(`/projects/${id}/members/${employeeId}`, { role }),
  removeMember: (id: string, employeeId: string) =>
    api.del<void>(`/projects/${id}/members/${employeeId}`),

  // Phase 3 — per-activity staffing (grouped read + assign/update/unassign).
  listAssignableEmployees: (id: string) =>
    api.get<AssignableEmployee[]>(`/projects/${id}/assignable-employees`),
  listActivityStaffing: (id: string) =>
    api.get<ActivityStaffing[]>(`/projects/${id}/activity-staffing`),
  assignActivityMember: (
    id: string,
    activityId: string,
    body: ActivityMemberCreateBody,
  ) =>
    api.post<ActivityMember>(
      `/projects/${id}/activity-staffing/${activityId}/members`,
      body,
    ),
  updateActivityMember: (
    id: string,
    activityId: string,
    employeeId: string,
    body: ActivityMemberUpdateBody,
  ) =>
    api.patch<ActivityMember>(
      `/projects/${id}/activity-staffing/${activityId}/members/${employeeId}`,
      body,
    ),
  removeActivityMember: (id: string, activityId: string, employeeId: string) =>
    api.del<void>(
      `/projects/${id}/activity-staffing/${activityId}/members/${employeeId}`,
    ),
};

/**
 * Stream the Weekly Report .xlsx for ONE project and ONE cycle, and trigger the
 * browser download.
 *
 * `cycle` is the currently selected one, passed explicitly - downloading while
 * "Previous Week" is on screen must never quietly fetch the current week. The
 * backend renders the same dataset the preview returned for that cycle, so the
 * file and the table always agree.
 *
 * Goes through fetch directly (not api-client) because the response is a binary
 * blob, not JSON - the same pattern as the PM activity and benchmark exports -
 * but still attaches the bearer token, and the endpoint re-checks Head
 * authority regardless.
 */
export async function downloadWeeklyReportXlsx(
  projectId: string,
  cycle: WeeklyReportCycle,
): Promise<void> {
  const res = await fetch(
    `${env.apiBaseUrl}${weeklyReportExportPath(projectId, cycle)}`,
    { headers: { Authorization: `Bearer ${getToken() ?? ""}` }, cache: "no-store" },
  );
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const filename =
    /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "WEEKLY REPORT.xlsx";
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
