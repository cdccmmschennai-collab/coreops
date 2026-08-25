"use client";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { useReportScope } from "@/features/work-reports/hooks";

import { ContinuationManagementPanel } from "./continuation-management-panel";

/**
 * The Lump-sum Activity Request review surface - its own page, reached from the
 * Homepage Shortcuts. Deliberately NOT a tab under /attendance: this is an
 * activity-reporting approval, unrelated to attendance or leave.
 *
 * Reviewer authority is "PM or assigned Project Head", which a role-based
 * RequireCapability guard cannot express (a Head has the plain `employee`
 * role), so the check is the same useReportScope lookup LeaveTab and
 * work-reports-view already make. The API enforces it server-side regardless.
 */
export function LumpSumActivityView() {
  const { role } = useAuth();
  const isManager = role === "project_manager";
  const scopeQuery = useReportScope({ enabled: !isManager });
  const isProjectHead = !isManager && scopeQuery.data?.is_project_head === true;
  const canReview = isManager || isProjectHead;

  if (!isManager && scopeQuery.isLoading) {
    return (
      <>
        <PageHeader title="Lump-sum Activity Requests" />
        <Skeleton className="h-64 w-full" />
      </>
    );
  }

  if (!canReview) {
    return (
      <ErrorState
        title="Not allowed"
        message="Only a project manager or an assigned Project Head can review lump-sum activity requests."
      />
    );
  }

  return (
    <>
      <PageHeader
        title="Lump-sum Activity Requests"
        subtitle="Approve or reject requests to continue a lump-sum activity past its allowed duration."
      />
      <ContinuationManagementPanel />
    </>
  );
}
