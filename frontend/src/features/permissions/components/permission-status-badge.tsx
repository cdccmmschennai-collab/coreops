import { Badge } from "@/components/ui/badge";

import {
  PERMISSION_STATUS_LABEL,
  PERMISSION_STATUS_VARIANT,
  type PermissionStatus,
} from "../types";

export function PermissionStatusBadge({ status }: { status: PermissionStatus }) {
  const label = PERMISSION_STATUS_LABEL[status] ?? status;
  return <Badge variant={PERMISSION_STATUS_VARIANT[status] ?? "neutral"}>{label}</Badge>;
}
