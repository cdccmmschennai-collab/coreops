import { Badge } from "@/components/ui/badge";
import type { LeaveStatus } from "../types";

const CONFIG: Record<LeaveStatus, { label: string; variant: "neutral" | "info" | "success" | "warning" | "danger" }> = {
  pending:   { label: "Pending",   variant: "warning" },
  approved:  { label: "Approved",  variant: "success" },
  rejected:  { label: "Rejected",  variant: "danger" },
  cancelled: { label: "Cancelled", variant: "neutral" },
};

export function LeaveStatusBadge({ status }: { status: LeaveStatus }) {
  const { label, variant } = CONFIG[status] ?? { label: status, variant: "neutral" };
  return <Badge variant={variant}>{label}</Badge>;
}
