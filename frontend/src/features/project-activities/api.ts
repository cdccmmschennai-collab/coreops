import { api } from "@/lib/api-client";
import type {
  ProjectActivity,
  ProjectActivityCreateBody,
  ProjectActivityUpdateBody,
} from "./types";

export const projectActivitiesApi = {
  list: (projectId: string) =>
    api.get<ProjectActivity[]>(`/projects/${projectId}/activities`),

  create: (projectId: string, body: ProjectActivityCreateBody) =>
    api.post<ProjectActivity>(`/projects/${projectId}/activities`, body),

  update: (projectId: string, id: string, body: ProjectActivityUpdateBody) =>
    api.patch<ProjectActivity>(`/projects/${projectId}/activities/${id}`, body),

  delete: (projectId: string, id: string) =>
    api.del<void>(`/projects/${projectId}/activities/${id}`),
};
