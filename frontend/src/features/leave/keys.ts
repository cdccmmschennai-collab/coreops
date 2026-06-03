import type { LeaveListParams } from "./types";

export const leaveKeys = {
  all: ["leave"] as const,
  list: (params: LeaveListParams) => [...leaveKeys.all, "list", params] as const,
  detail: (id: string) => [...leaveKeys.all, "detail", id] as const,
};
