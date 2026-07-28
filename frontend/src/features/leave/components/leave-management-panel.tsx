"use client";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { useLeaveList } from "../hooks";
import { resolveLeaveQueue } from "../types";
import { AdminLeaveList } from "./admin-leave-list";
import { LeaveCancellationReviewPanel } from "./leave-cancellation-review-panel";
import { LeaveReviewPanel } from "./leave-review-panel";

interface Props {
  employeeId?: string;
}

/** The project manager's Leave tab: three queues behind an inner tab strip,
 *  so cancellation review lives inside Leave rather than adding another
 *  top-level Attendance tab.
 *
 *  Counts come from API totals, never `items.length` — the lists are paged. */
export function LeaveManagementPanel({ employeeId }: Props) {
  const [rawQueue, setQueue] = useUrlState("queue", "pending");
  const queue = resolveLeaveQueue(rawQueue);

  // limit:1 — these two only exist to read `total` for the badges.
  const pendingCount =
    useLeaveList({ status: "pending", limit: 1, offset: 0 }).data?.total ?? 0;
  const cancellationCount =
    useLeaveList({ status: "cancellation_requested", limit: 1, offset: 0 }).data?.total ?? 0;

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
          { value: "all", label: "All leave" },
        ]}
        value={queue}
        onChange={setQueue}
      />

      {queue === "pending" && <LeaveReviewPanel employeeId={employeeId} />}
      {queue === "cancellation" && <LeaveCancellationReviewPanel />}
      {queue === "all" && <AdminLeaveList />}
    </div>
  );
}
