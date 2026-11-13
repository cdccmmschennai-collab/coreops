import { api } from "@/lib/api-client";

import type {
  Deliverable,
  DeliverableAssignee,
  DeliverableChange,
  DeliverableCreateBody,
  DeliverableUpdateBody,
} from "./types";

export const deliverablesApi = {
  listAll: () =>
    api.get<Deliverable[]>(`/deliverables`),

  get: (id: string) =>
    api.get<Deliverable>(`/deliverables/${id}`),

  changes: (id: string) =>
    api.get<DeliverableChange[]>(`/deliverables/${id}/changes`),

  list: (projectId: string) =>
    api.get<Deliverable[]>(`/projects/${projectId}/deliverables`),

  assignees: (projectId: string) =>
    api.get<DeliverableAssignee[]>(`/projects/${projectId}/deliverables/assignees`),

  create: (projectId: string, body: DeliverableCreateBody) =>
    api.post<Deliverable>(`/projects/${projectId}/deliverables`, body),

  update: (projectId: string, id: string, body: DeliverableUpdateBody) =>
    api.patch<Deliverable>(`/projects/${projectId}/deliverables/${id}`, body),

  delete: (projectId: string, id: string) =>
    api.del<void>(`/projects/${projectId}/deliverables/${id}`),
};
