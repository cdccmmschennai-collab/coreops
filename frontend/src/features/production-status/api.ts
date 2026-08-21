import { api } from "@/lib/api-client";

import type {
  ProductionStatus,
  ProductionStatusCreateBody,
  ProductionStatusHistoryParams,
} from "./types";

function historyQuery(params: ProductionStatusHistoryParams): string {
  const sp = new URLSearchParams();
  if (params.activityId) sp.set("activity_id", params.activityId);
  if (params.revision) sp.set("revision", params.revision);
  const q = sp.toString();
  return q ? `?${q}` : "";
}

/**
 * The three Phase 1 endpoints, and only those.
 *
 * There is no update and no delete because the backend has neither: production
 * status is append-only, so a correction is a new POST that supersedes the
 * previous row without touching it.
 */
export const productionStatusApi = {
  /** Current status of every (revision, activity) - derived server-side. */
  listLatest: (projectId: string) =>
    api.get<ProductionStatus[]>(`/projects/${projectId}/production-status`),

  /** Every recorded update, newest first; optionally one activity/revision. */
  listHistory: (projectId: string, params: ProductionStatusHistoryParams = {}) =>
    api.get<ProductionStatus[]>(
      `/projects/${projectId}/production-status/history${historyQuery(params)}`,
    ),

  /** Append ONE update. Never a PATCH/PUT - see the module note above. */
  create: (projectId: string, body: ProductionStatusCreateBody) =>
    api.post<ProductionStatus>(`/projects/${projectId}/production-status`, body),
};
