"use client";

import { useSearchParams } from "next/navigation";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

interface Props {
  employeeId?: string;
}

/** A Project Head keeps their own employee Leave history AND gets the same
 *  approval UI a PM has (Pending/Cancellation/All), scoped server-side to the
 *  projects they Head via `authz.reviewable_project_ids` - no client-side
 *  filtering needed, the same `useLeaveList` calls PM's panel already makes
 *  come back pre-scoped for a Head actor.
 *
 *  Defaults to "My leave" so a Head landing on the tab cold sees exactly what
 *  a plain employee always saw; the homepage shortcut
 *  (?tab=leave&queue=pending) forces "Team approvals" straight open by
 *  checking for a `queue` param before applying that default. */
export function HeadLeaveTab({ employeeId }: Props) {
  const searchParams = useSearchParams();
  const hasQueueParam = searchParams.get("queue") !== null;
  const [view, setView] = useUrlState("view", hasQueueParam ? "team" : "my");

  return (
    <div className="space-y-4">
      <Tabs
        items={[
          { value: "my", label: "My leave" },
          { value: "team", label: "Team approvals" },
        ]}
        value={view}
        onChange={setView}
      />
      {view === "my" && <LeaveHistory employeeId={employeeId} />}
      {view === "team" && (
        <LeaveManagementPanel employeeId={employeeId} showPermissionQueue={false} />
      )}
    </div>
  );
}
