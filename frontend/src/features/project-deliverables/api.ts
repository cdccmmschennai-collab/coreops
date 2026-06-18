import { api } from "@/lib/api-client";

import type {
  Deliverable,
  DeliverableCreateBody,
  DeliverableUpdateBody,
} from "./types";

export const deliverablesApi = {
  listAll: () =>
    api.get<Deliverable[]>(`/deliverables`),

  list: (projectId: string) =>
    api.get<Deliverable[]>(`/projects/${projectId}/deliverables`),

  create: (projectId: string, body: DeliverableCreateBody) =>
    api.post<Deliverable>(`/projects/${projectId}/deliverables`, body),

  update: (projectId: string, id: string, body: DeliverableUpdateBody) =>
    api.patch<Deliverable>(`/projects/${projectId}/deliverables/${id}`, body),

  delete: (projectId: string, id: string) =>
    api.del<void>(`/projects/${projectId}/deliverables/${id}`),
};
