import { api } from "@/lib/api-client";

import type {
  ActivityMember,
  ActivityMemberCreateBody,
  ActivityMemberUpdateBody,
  ActivityStaffing,
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
  ProjectTimelineEvent,
  ProjectUpdateBody,
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
