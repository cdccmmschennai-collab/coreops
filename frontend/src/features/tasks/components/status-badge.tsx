import { Badge } from "@/components/ui/badge";

import { TASK_PRIORITY_LABEL, TASK_STATUS_LABEL } from "../schemas";
import type { TaskPriority, TaskStatus } from "../types";

const STATUS_VARIANT: Record<TaskStatus, "neutral" | "info" | "success" | "warning"> = {
  open: "neutral",
  in_progress: "info",
  completed: "success",
  cancelled: "warning",
};

const PRIORITY_VARIANT: Record<TaskPriority, "neutral" | "info" | "warning"> = {
  low: "neutral",
  medium: "info",
  high: "warning",
};

export function StatusBadge({ status }: { status: TaskStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]} dot>
      {TASK_STATUS_LABEL[status]}
    </Badge>
  );
}

export function PriorityBadge({ priority }: { priority: TaskPriority }) {
  return (
    <Badge variant={PRIORITY_VARIANT[priority]}>
      {TASK_PRIORITY_LABEL[priority]}
    </Badge>
  );
}
