"use client";

import { Tabs } from "@/components/ui/tabs";
import { PermissionReviewPanel } from "@/features/permissions/components/permission-review-panel";
import { usePermissionList } from "@/features/permissions/hooks";
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveList } from "../hooks";
import { resolveLeaveQueue } from "../types";
import { AdminLeaveList } from "./admin-leave-list";
import { LeaveCancellationReviewPanel } from "./leave-cancellation-review-panel";
import { LeaveReviewPanel } from "./leave-review-panel";

interface Props {
  employeeId?: string;
  /** A Project Head gets Pending/Cancellation/All (leave only) - Permission
   *  Requests is an unrelated, PM-only attendance-permission domain and stays
   *  hidden for a Head, per Phase 1's leave-only scope. Defaults to true so
   *  every existing PM call site is unaffected. */
  showPermissionQueue?: boolean;
}

/** The project manager's Leave tab: three queues behind an inner tab strip,
 *  so cancellation review lives inside Leave rather than adding another
 *  top-level Attendance tab.
 *
 *  Counts come from API totals, never `items.length` — the lists are paged. */
export function LeaveManagementPanel({ employeeId, showPermissionQueue = true }: Props) {
  const [rawQueue, setQueue] = useUrlState("queue", "pending");
  const queue = resolveLeaveQueue(rawQueue);

  // `showPermissionQueue` is only ever passed `false` for a Project Head's
  // reused panel (the Permission-requests queue is unrelated, PM-only). Reused
  // here as the "am I rendering for a Head" signal rather than adding a second
  // prop: a Head's own requests must not appear in their own approval queues.
  const excludeSelf = !showPermissionQueue;

  // limit:1 — these two only exist to read `total` for the badges.
  const pendingCount =
    useLeaveList({ status: "pending", limit: 1, offset: 0 }).data?.total ?? 0;
  const cancellationCount =
    useLeaveList({ status: "cancellation_requested", limit: 1, offset: 0 }).data?.total ?? 0;
  const permissionCount =
    usePermissionList(
      { status: "pending", limit: 1, offset: 0 },
      { enabled: showPermissionQueue },
    ).data?.total ?? 0;

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          {
            value: "pending",
            label: "Pending requests",
            count: pendingCount || undefined,
            countVariant: "warning",
          },
          {
            value: "cancellation",
            label: "Cancellation requests",
            count: cancellationCount || undefined,
            countVariant: "info",
          },
          ...(showPermissionQueue
            ? [{
                value: "permission",
                label: "Permission requests",
                count: permissionCount || undefined,
                countVariant: "warning" as const,
              }]
            : []),
          { value: "all", label: "All leave" },
        ]}
        value={queue}
        onChange={setQueue}
      />

      {queue === "pending" && (
        <LeaveReviewPanel employeeId={employeeId} excludeSelf={excludeSelf} />
      )}
      {queue === "cancellation" && <LeaveCancellationReviewPanel excludeSelf={excludeSelf} />}
      {queue === "permission" && showPermissionQueue && <PermissionReviewPanel />}
      {queue === "all" && <AdminLeaveList excludeSelf={excludeSelf} />}
    </div>
  );
}
