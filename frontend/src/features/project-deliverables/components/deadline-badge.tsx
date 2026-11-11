import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

import { DEADLINE_STATE_LABEL } from "../reminders";
import type { DeadlineState } from "../types";

type Variant = "neutral" | "warning" | "danger" | "success" | "outline";

/**
 * Visual treatment per backend deadline state (ADR-003 Amendment 2):
 *   on_track / no_deadline  neutral
 *   due_soon                amber
 *   urgent                  amber, emphasised
 *   due_today               solid amber - the most prominent non-red state
 *   overdue                 red
 *   completed               green
 */
const VARIANT: Record<DeadlineState, Variant> = {
  overdue: "danger",
  due_today: "warning",
  urgent: "warning",
  due_soon: "warning",
  on_track: "neutral",
  no_deadline: "outline",
  completed: "success",
};

const EXTRA: Partial<Record<DeadlineState, string>> = {
  due_today: "border-warning bg-warning text-warning-foreground font-semibold",
  urgent: "border-warning/50 font-semibold",
  overdue: "font-semibold",
};

export function DeadlineBadge({
  state,
  className,
}: {
  state: DeadlineState;
  className?: string;
}) {
  return (
    <Badge
      variant={VARIANT[state]}
      dot={state !== "due_today"}
      className={cn(EXTRA[state], className)}
      data-state={state}
    >
      {DEADLINE_STATE_LABEL[state]}
    </Badge>
  );
}
