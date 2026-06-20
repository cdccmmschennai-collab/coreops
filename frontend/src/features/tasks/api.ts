import { api } from "@/lib/api-client";

import type {
  AssignableProject,
  Task,
  TaskCreateBody,
  TaskListParams,
  TaskPage,
  TaskStatusUpdateBody,
  TaskUpdateBody,
} from "./types";

function toQuery(p: TaskListParams): string {
  const sp = new URLSearchParams();
  if (p.mine !== undefined) sp.set("mine", String(p.mine));
  if (p.q) sp.set("q", p.q);
  if (p.status) sp.set("status", p.status);
  if (p.priority) sp.set("priority", p.priority);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const tasksApi = {
  list: (params: TaskListParams) => api.get<TaskPage>(`/tasks?${toQuery(params)}`),
  get: (id: string) => api.get<Task>(`/tasks/${id}`),
  create: (body: TaskCreateBody) => api.post<Task>("/tasks", body),
  update: (id: string, body: TaskUpdateBody) => api.patch<Task>(`/tasks/${id}`, body),
  updateStatus: (id: string, body: TaskStatusUpdateBody) =>
    api.patch<Task>(`/tasks/${id}/status`, body),
  assignableProjects: () =>
    api.get<AssignableProject[]>("/tasks/assignable-projects"),
};
