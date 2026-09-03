"use client";

import { useSearchParams } from "next/navigation";

import { Tabs } from "@/components/ui/tabs";
import { useUrlState } from "@/lib/use-url-state";

import { resolveLeaveView } from "../types";
import { LeaveHistory } from "./leave-history";
import { LeaveManagementPanel } from "./leave-management-panel";

interface Props {
  employeeId?: string;
}

/** A Project Head keeps their own employee Leave history AND gets the same
 *  approval UI a PM has (Pending/Cancellation/Permission/All), scoped
 *  server-side to the projects they Head via `authz.reviewable_project_ids` - no
 *  client-side filtering needed, the same `useLeaveList` / `usePermissionList`
 *  calls PM's panel already makes come back pre-scoped for a Head actor.
 *
 *  Permission requests joined this set in Phase 4D: a permission routed to a
 *  Head's project has been reviewable by that Head since Phase 4B, so the queue
 *  was simply missing from the one place they could have acted on it.
 *
 *  Defaults to "My leave" so a Head landing on the tab cold sees exactly what
 *  a plain employee always saw; the homepage shortcut and the leave
 *  notifications (?tab=leave&queue=pending) force "Team approvals" straight
 *  open by naming a queue - see `resolveLeaveView`. */
export function HeadLeaveTab({ employeeId }: Props) {
  const searchParams = useSearchParams();
  const hasQueueParam = searchParams.get("queue") !== null;
  // Fallback "" rather than "my": `useUrlState` strips a value equal to its
  // fallback from the URL, so with "my" as the fallback NEITHER choice was
  // durable - "my" was erased, and "team" was only implied by `queue`, which is
  // itself erased the moment the Pending queue is selected. Both are now
  // written explicitly, which is exactly what browser Back reads back.
  const [rawView, setView] = useUrlState("view", "");
  const view = resolveLeaveView(rawView, hasQueueParam);

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
        <LeaveManagementPanel employeeId={employeeId} excludeSelf />
      )}
    </div>
  );
}
