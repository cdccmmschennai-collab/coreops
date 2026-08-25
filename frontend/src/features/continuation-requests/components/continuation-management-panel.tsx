"use client";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { usePendingContinuationRequests } from "../hooks";
import { AllContinuationRequestsList } from "./all-continuation-requests-list";
import { ContinuationReviewPanel } from "./continuation-review-panel";

export function ContinuationManagementPanel() {
  const [queue, setQueue] = useUrlState("queue", "pending");
  const pendingCount = usePendingContinuationRequests().data?.length ?? 0;

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          {
            value: "pending",
            label: "Pending Requests",
            count: pendingCount || undefined,
            countVariant: "warning",
          },
          { value: "all", label: "All Requests" },
        ]}
        value={queue}
        onChange={setQueue}
      />
      {queue === "pending" && <ContinuationReviewPanel />}
      {queue === "all" && <AllContinuationRequestsList />}
    </div>
  );
}
