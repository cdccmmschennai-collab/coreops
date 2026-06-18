import { Badge } from "@/components/ui/badge";
import type { BadgeProps } from "@/components/ui/badge";

import type { SubmissionStatus } from "../types";
import { SUBMISSION_STATUS_LABEL } from "../types";

const VARIANT: Record<SubmissionStatus, BadgeProps["variant"]> = {
  draft: "neutral",
  submitted: "info",
  approved: "success",
  rejected: "danger",
};

export function SubmissionStatusBadge({ status }: { status: SubmissionStatus }) {
  return (
    <Badge variant={VARIANT[status]} dot>
      {SUBMISSION_STATUS_LABEL[status]}
    </Badge>
  );
}
