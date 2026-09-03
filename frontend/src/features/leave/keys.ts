import type { LeaveListParams } from "./types";

export const leaveKeys = {
  all: ["leave"] as const,
  list: (params: LeaveListParams) => [...leaveKeys.all, "list", params] as const,
  detail: (id: string) => [...leaveKeys.all, "detail", id] as const,
  deliverableImpact: (ids: string[]) =>
    [...leaveKeys.all, "deliverable-impact", ids] as const,
  attendanceSummary: (ids: string[]) =>
    [...leaveKeys.all, "attendance-summary", ids] as const,
  classificationPreview: (start: string, end: string) =>
    [...leaveKeys.all, "classification-preview", start, end] as const,
};
