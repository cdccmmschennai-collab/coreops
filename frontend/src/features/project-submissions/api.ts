import { api } from "@/lib/api-client";

import type {
  Submission,
  SubmissionCreateBody,
  SubmissionStatusUpdateBody,
  SubmissionUpdateBody,
} from "./types";

export const submissionsApi = {
  list: (projectId: string) =>
    api.get<Submission[]>(`/projects/${projectId}/submissions`),
  get: (projectId: string, id: string) =>
    api.get<Submission>(`/projects/${projectId}/submissions/${id}`),
  create: (projectId: string, body: SubmissionCreateBody) =>
    api.post<Submission>(`/projects/${projectId}/submissions`, body),
  update: (projectId: string, id: string, body: SubmissionUpdateBody) =>
    api.patch<Submission>(`/projects/${projectId}/submissions/${id}`, body),
  updateStatus: (projectId: string, id: string, body: SubmissionStatusUpdateBody) =>
    api.patch<Submission>(`/projects/${projectId}/submissions/${id}/status`, body),
  delete: (projectId: string, id: string) =>
    api.del<void>(`/projects/${projectId}/submissions/${id}`),
};
