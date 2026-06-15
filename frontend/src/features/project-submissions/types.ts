import type { components } from "@/types/openapi";

export type SubmissionStatus = components["schemas"]["SubmissionStatus"];
export type SubmissionItemIn = components["schemas"]["SubmissionItemIn"];
export type SubmissionItemOut = components["schemas"]["SubmissionItemOut"];
export type SubmissionCreateBody = components["schemas"]["SubmissionCreate"];
export type SubmissionUpdateBody = components["schemas"]["SubmissionUpdate"];
export type SubmissionStatusUpdateBody = components["schemas"]["SubmissionStatusUpdate"];
export type Submission = components["schemas"]["SubmissionOut"];

export const SUBMISSION_STATUS_LABEL: Record<SubmissionStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  approved: "Approved",
  rejected: "Rejected",
};
