"use client";

import { EmptyState } from "@/components/feedback/empty-state";
import { useAuth } from "@/features/auth/auth-provider";

import { compOffView } from "../types";
import { CompOffList } from "./comp-off-list";
import { CompOffRequestForm } from "./comp-off-request-form";
import { CompOffReviewPanel } from "./comp-off-review-panel";

/** Role-aware Comp Off tab content embedded inside the Attendance page.
 *
 *  Employees (Project Heads included - comp off has no Head routing) get the
 *  request form and their own requests. Project managers get the pending queue
 *  and every request. Which rows each sees is decided by the SERVER: a
 *  non-manager's list is scoped to their own requests whatever is asked for. */
export function CompOffTab() {
  const { role, employeeId } = useAuth();
  const viewer = { role, employeeId };
  const { canRequest, canReview } = compOffView(viewer);

  if (canReview) {
    return (
      <div className="space-y-4">
        <CompOffReviewPanel viewer={viewer} />
        <CompOffList title="All comp off requests" viewer={viewer} showEmployee />
      </div>
    );
  }

  if (canRequest) {
    return (
      <div className="space-y-4">
        <CompOffRequestForm />
        <CompOffList title="My comp off requests" viewer={viewer} />
      </div>
    );
  }

  return (
    <EmptyState
      title="No employee profile"
      description="Your account isn't linked to an employee profile, so you can't request a comp off. Ask your manager to link your employee record."
    />
  );
}
