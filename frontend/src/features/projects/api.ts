import { api } from "@/lib/api-client";

import type {
  Project,
  ProjectCreateBody,
  ProjectListParams,
  ProjectMember,
  ProjectMemberCreateBody,
  ProjectMemberRole,
  ProjectPage,
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

  listMembers: (id: string) => api.get<ProjectMember[]>(`/projects/${id}/members`),
  addMember: (id: string, body: ProjectMemberCreateBody) =>
    api.post<ProjectMember>(`/projects/${id}/members`, body),
  updateMemberRole: (id: string, employeeId: string, role: ProjectMemberRole) =>
    api.patch<ProjectMember>(`/projects/${id}/members/${employeeId}`, { role }),
  removeMember: (id: string, employeeId: string) =>
    api.del<void>(`/projects/${id}/members/${employeeId}`),
};
