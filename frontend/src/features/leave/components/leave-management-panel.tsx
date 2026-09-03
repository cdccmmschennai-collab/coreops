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
  /** Drop the viewer's OWN requests from every queue here. Passed `true` only by
   *  a Project Head's reused panel: a Head is an employee who files their own
   *  requests, and nobody reviews their own, so their rows must not sit in the
   *  queues they are working through. Defaults to false, which is exactly what
   *  every existing PM call site got and still gets.
   *
   *  This used to be inferred from `showPermissionQueue`, which no longer exists:
   *  Phase 4D gives a Head the Permission requests queue too, so the two facts
   *  had to stop being the same flag. */
  excludeSelf?: boolean;
}

/** The approval Leave tab - a project manager's, and since Phase 4D a Project
 *  Head's: four queues behind an inner tab strip, so cancellation and permission
 *  review live inside Leave rather than adding more top-level Attendance tabs.
 *
 *  WHICH ROWS EACH READER SEES IS NOT DECIDED HERE. Both `/leave-requests` and
 *  `/permission-requests` are already scoped server-side to the projects the
 *  caller heads (a PM sees everything), so the same calls serve both and the
 *  backend stays the only thing deciding access.
 *
 *  Counts come from API totals, never `items.length` — the lists are paged. */
export function LeaveManagementPanel({ employeeId, excludeSelf = false }: Props) {
  // Fallback "" rather than "pending": `useUrlState` strips a value equal to its
  // fallback, so selecting Pending used to ERASE `queue` from the URL - which
  // both lost the queue on Back and, for a Head, took the only signal that they
  // were on Team approvals with it. `resolveLeaveQueue` still maps "" (and any
  // stale value) to the pending queue, so the default is unchanged.
  const [rawQueue, setQueue] = useUrlState("queue", "");
  const queue = resolveLeaveQueue(rawQueue);

  // These two only exist to read `total` for the badges. They MUST pass the same
  // `excludeSelf` the queues below pass, or a Head's own request is counted on a
  // tab whose list will not show it - see `leaveQueueCountParams`.
  const pendingCount =
    useLeaveList(leaveQueueCountParams("pending", excludeSelf)).data?.total ?? 0;
  // The Cancellation queue holds BOTH kinds since Phase 4E, so its badge is the
  // sum of both totals - counting only the leave half would understate a queue
  // the reviewer can see permission rows in.
  const leaveCancellationCount =
    useLeaveList(leaveQueueCountParams("cancellation_requested", excludeSelf)).data?.total ?? 0;
  const permissionCancellationCount =
    usePermissionList({
      status: "cancellation_requested",
      limit: 1,
      offset: 0,
      exclude_self: excludeSelf,
    }).data?.total ?? 0;
  const cancellationCount = leaveCancellationCount + permissionCancellationCount;
  // Same rule as the two above: the badge and the list it labels must describe
  // ONE dataset, so it passes the same `exclude_self` the queue passes.
  const permissionCount =
    usePermissionList({
      status: "pending",
      limit: 1,
      offset: 0,
      exclude_self: excludeSelf,
    }).data?.total ?? 0;

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
          {
            value: "permission",
            label: "Permission requests",
            count: permissionCount || undefined,
            countVariant: "warning",
          },
          // Phase 4F: the label changed, the KEY deliberately did not. `all` is
          // in existing bookmarks, in every `from=` address a detail page was
          // opened with, and in the browser's history - renaming it would break
          // Back for no gain. The tab now holds permission rows beside leave
          // (see `AdminLeaveList`), which is what "All Requests" means.
          { value: "all", label: "All Requests" },
        ]}
        value={queue}
        onChange={setQueue}
      />

      {queue === "pending" && (
        <LeaveReviewPanel employeeId={employeeId} excludeSelf={excludeSelf} />
      )}
      {queue === "cancellation" && <LeaveCancellationReviewPanel excludeSelf={excludeSelf} />}
      {queue === "permission" && <PermissionReviewPanel excludeSelf={excludeSelf} />}
      {queue === "all" && <AdminLeaveList excludeSelf={excludeSelf} />}
    </div>
  );
}
