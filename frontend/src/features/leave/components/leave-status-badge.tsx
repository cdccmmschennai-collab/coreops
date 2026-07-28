import { Badge } from "@/components/ui/badge";

import { LEAVE_STATUS_LABEL } from "../types";
import type { LeaveStatus } from "../types";

const VARIANT: Record<LeaveStatus, "neutral" | "info" | "success" | "warning" | "danger"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  cancelled: "neutral",
  // Still active leave, awaiting a manager decision — informational rather than
  // success, so it reads as "in review" instead of settled.
  cancellation_requested: "info",
};

export function LeaveStatusBadge({ status }: { status: LeaveStatus }) {
  const label = LEAVE_STATUS_LABEL[status] ?? status;
  return <Badge variant={VARIANT[status] ?? "neutral"}>{label}</Badge>;
}
