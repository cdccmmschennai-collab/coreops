/**
 * Rework Activity Approval - the employee-facing state of one report row.
 *
 * Pure (no React) so `node --test` can pin it. Two inputs only:
 *   requiresApproval - the selected sub-activity's requires_pm_approval flag
 *                      (Activity Master configuration, migration 0090);
 *   status           - the row's server-resolved rework_approval_status
 *                      (null until the report is submitted).
 *
 * The backend decides authoritatively at submit; this only labels it.
 */

export type ReworkApprovalStatus = "pending" | "approved" | "rejected" | "cancelled";

export type ReworkBadgeTone = "warning" | "success" | "danger";

export interface ReworkRowBadge {
  label: string;
  tone: ReworkBadgeTone;
}

/** Shown under the selectors before the report is submitted. */
export const PM_APPROVAL_REQUIRED_LABEL = "PM Approval Required";
export const PM_APPROVAL_REQUIRED_MESSAGE =
  "This activity requires Project Manager approval. Your report will be submitted for review.";

export function reworkRowBadge(
  requiresApproval: boolean,
  status: ReworkApprovalStatus | string | null | undefined,
): ReworkRowBadge | null {
  switch (status) {
    case "pending":
      return { label: "In Review", tone: "warning" };
    case "approved":
      return { label: "Approved", tone: "success" };
    case "rejected":
      return { label: "Rejected - Action Required", tone: "danger" };
    default:
      // Not submitted yet (or a cancelled cycle): only the configuration speaks.
      return requiresApproval ? { label: PM_APPROVAL_REQUIRED_LABEL, tone: "warning" } : null;
  }
}
