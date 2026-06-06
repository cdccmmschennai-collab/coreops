import { api } from "@/lib/api-client";

import type { AuditListParams, AuditLogPage } from "./types";

function toQuery(p: AuditListParams): string {
  const sp = new URLSearchParams();
  if (p.action) sp.set("action", p.action);
  if (p.status) sp.set("status", p.status);
  if (p.entity_type) sp.set("entity_type", p.entity_type);
  sp.set("limit", String(p.limit));
  sp.set("offset", String(p.offset));
  return sp.toString();
}

export const auditApi = {
  list: (params: AuditListParams) => api.get<AuditLogPage>(`/audit-logs?${toQuery(params)}`),
};
