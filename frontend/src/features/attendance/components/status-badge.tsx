import { Badge } from "@/components/ui/badge";

import { ATTENDANCE_STATUS_LABEL } from "../schemas";
import type { AttendanceStatus } from "../types";

const VARIANT: Record<
  AttendanceStatus,
  "success" | "danger" | "warning" | "info" | "neutral" | "teal"
> = {
  present: "success",
  absent: "danger",
  half_day: "warning",
  leave: "warning",
  comp_off: "teal",
  holiday: "info",
  weekend: "neutral",
};

export function StatusBadge({ status }: { status: AttendanceStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {ATTENDANCE_STATUS_LABEL[status]}
    </Badge>
  );
}
