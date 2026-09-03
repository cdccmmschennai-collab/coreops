import type { AllRequestListParams } from "./all-requests";
import type { LeaveListParams } from "./types";

export const leaveKeys = {
  all: ["leave"] as const,
  list: (params: LeaveListParams) => [...leaveKeys.all, "list", params] as const,
  // Under the leave root on purpose: a leave mutation invalidates `leaveKeys.all`
  // and the All Requests table has to refresh with it. Permission mutations
  // invalidate their own root, so the hook below is registered under both.
  allRequests: (params: AllRequestListParams) =>
    [...leaveKeys.all, "all-requests", params] as const,
  detail: (id: string) => [...leaveKeys.all, "detail", id] as const,
  deliverableImpact: (ids: string[]) =>
    [...leaveKeys.all, "deliverable-impact", ids] as const,
  attendanceSummary: (ids: string[]) =>
    [...leaveKeys.all, "attendance-summary", ids] as const,
  classificationPreview: (start: string, end: string) =>
    [...leaveKeys.all, "classification-preview", start, end] as const,
};
