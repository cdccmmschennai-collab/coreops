import type { components } from "@/types/openapi";

// Types come straight from the live API contract (openapi-typescript output).
export type AuditLog = components["schemas"]["AuditLogOut"];
export type AuditLogPage = components["schemas"]["AuditLogPage"];

export interface AuditListParams {
  action: string;
  status: string;
  entity_type: string;
  limit: number;
  offset: number;
}
