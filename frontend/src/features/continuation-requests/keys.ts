import type { ContinuationRequestListParams } from "./types";

export const continuationRequestKeys = {
  all: ["continuation-requests"] as const,
  pending: () => [...continuationRequestKeys.all, "pending"] as const,
  list: (params: ContinuationRequestListParams) =>
    [...continuationRequestKeys.all, "list", params] as const,
  detail: (id: string) => [...continuationRequestKeys.all, "detail", id] as const,
};
