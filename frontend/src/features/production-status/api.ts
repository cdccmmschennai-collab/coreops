import { api } from "@/lib/api-client";
import { getToken } from "@/lib/auth-storage";
import { env } from "@/lib/env";

import type {
  ProductionStatus,
  ProductionStatusCreateBody,
  ProductionStatusHistoryParams,
  ProductionStatusReport,
} from "./types";

/** The PM report's two routes. One dataset, two representations. */
const REPORT_PATH = "/production-status/report";
const REPORT_XLSX_PATH = "/production-status/report.xlsx";

function historyQuery(params: ProductionStatusHistoryParams): string {
  const sp = new URLSearchParams();
  if (params.activityId) sp.set("activity_id", params.activityId);
  if (params.revision) sp.set("revision", params.revision);
  const q = sp.toString();
  return q ? `?${q}` : "";
}

/**
 * The three Phase 1 per-project endpoints plus the Phase 4 PM report.
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

  /**
   * The PM cumulative report - every project's current status in ONE request.
   *
   * Deliberately not a loop over the project list calling `listLatest`: that
   * would be N requests, and N separately-ordered result sets the client would
   * then have to merge and number itself. The backend does the whole thing in
   * one query.
   */
  report: () => api.get<ProductionStatusReport>(REPORT_PATH),
};

/**
 * Download the report as .xlsx.
 *
 * Outside `productionStatusApi` because it is not a JSON call: it goes through
 * plain `fetch` to get at the blob and the Content-Disposition filename, which
 * is the same shape `downloadWeeklyReportXlsx` uses for every other CoreOps
 * export. The file is built by the backend from the same service call the
 * preview reads, so no data is re-derived here - this function only saves it.
 */
export async function downloadProductionStatusReportXlsx(): Promise<void> {
  const res = await fetch(`${env.apiBaseUrl}${REPORT_XLSX_PATH}`, {
    headers: { Authorization: `Bearer ${getToken() ?? ""}` },
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Export failed (${res.status})`);
  const disposition = res.headers.get("content-disposition") ?? "";
  const filename =
    /filename="?([^";]+)"?/.exec(disposition)?.[1] ?? "PRODUCTION STATUS.xlsx";
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
