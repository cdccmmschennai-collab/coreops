import { Badge } from "@/components/ui/badge";

import { PERMISSION_STATUS_LABEL, type PermissionStatus } from "../types";

const VARIANT: Record<PermissionStatus, "neutral" | "success" | "warning" | "danger"> = {
  pending: "warning",
  approved: "success",
  rejected: "danger",
  cancelled: "neutral",
  // "Info" is not a variant here, so a withdrawal awaiting a decision reads as
  // the open item it is - the same warning tone a pending request gets.
  cancellation_requested: "warning",
};

export function PermissionStatusBadge({ status }: { status: PermissionStatus }) {
  const label = PERMISSION_STATUS_LABEL[status] ?? status;
  return <Badge variant={VARIANT[status] ?? "neutral"}>{label}</Badge>;
}
