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
      params.revision ?? "",
    ] as const,
};
