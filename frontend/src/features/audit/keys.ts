import type { AuditListParams } from "./types";

export const auditKeys = {
  all: ["audit"] as const,
  list: (params: AuditListParams) => ["audit", "list", params] as const,
};
