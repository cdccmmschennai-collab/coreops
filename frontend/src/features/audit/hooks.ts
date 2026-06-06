import { useQuery } from "@tanstack/react-query";

import { auditApi } from "./api";
import { auditKeys } from "./keys";
import type { AuditListParams } from "./types";

/** Paginated, filterable audit trail (project_manager only). */
export function useAuditLogs(params: AuditListParams) {
  return useQuery({
    queryKey: auditKeys.list(params),
    queryFn: () => auditApi.list(params),
    placeholderData: (prev) => prev,
  });
}
