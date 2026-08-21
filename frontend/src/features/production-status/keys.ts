import type { ProductionStatusHistoryParams } from "./types";

export const productionStatusKeys = {
  all: ["production-status"] as const,
  /** Latest per (revision, activity) for one project. */
  latest: (projectId: string) => ["production-status", "latest", projectId] as const,
  /** The filter is part of the key: "all history" and "REV-0 / FMTL history"
   *  are two different datasets, so opening one must never render the other. */
  history: (projectId: string, params: ProductionStatusHistoryParams) =>
    [
      "production-status",
      "history",
      projectId,
      params.activityId ?? "",
      params.activityLabel ?? "",
      params.revision ?? "",
    ] as const,
  /** The PM cumulative report. No project in the key - it spans all of them.
   *  The month IS in the key: "All Months" and "August 2026" are two different
   *  datasets, so switching the dropdown must fetch rather than re-render the
   *  other month's rows. "" is All Months. */
  report: (month?: string) => ["production-status", "report", month ?? ""] as const,
};
