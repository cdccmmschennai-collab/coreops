"use client";

import { Tabs } from "@/components/ui/tabs";
import { PermissionReviewPanel } from "@/features/permissions/components/permission-review-panel";
import { usePermissionList } from "@/features/permissions/hooks";
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveList } from "../hooks";
import { leaveQueueCountParams, resolveLeaveQueue } from "../types";
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
  // Fallback "" rather than "pending": `useUrlState` strips a value equal to its
  // fallback, so selecting Pending used to ERASE `queue` from the URL - which
  // both lost the queue on Back and, for a Head, took the only signal that they
  // were on Team approvals with it. `resolveLeaveQueue` still maps "" (and any
  // stale value) to the pending queue, so the default is unchanged.
  const [rawQueue, setQueue] = useUrlState("queue", "");
  const queue = resolveLeaveQueue(rawQueue);

  // `showPermissionQueue` is only ever passed `false` for a Project Head's
  // reused panel (the Permission-requests queue is unrelated, PM-only). Reused
  // here as the "am I rendering for a Head" signal rather than adding a second
  // prop: a Head's own requests must not appear in their own approval queues.
  const excludeSelf = !showPermissionQueue;

  // These two only exist to read `total` for the badges. They MUST pass the same
  // `excludeSelf` the queues below pass, or a Head's own request is counted on a
  // tab whose list will not show it - see `leaveQueueCountParams`.
  const pendingCount =
    useLeaveList(leaveQueueCountParams("pending", excludeSelf)).data?.total ?? 0;
  const cancellationCount =
    useLeaveList(leaveQueueCountParams("cancellation_requested", excludeSelf)).data?.total ?? 0;
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
