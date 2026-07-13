"use client";

import { useUrlState } from "@/lib/use-url-state";

import { AuditLogFilters, type AuditFilterValues } from "./audit-log-filters";
import { AuditLogTable } from "./audit-log-table";
import { useAuditLogs } from "../hooks";
import type { AuditListParams } from "../types";

const LIMIT = 20;

export function AuditLogView() {
  // Filters/page persist in the URL (namespaced au_* so they don't clash with
  // the other Settings tabs that share this route) so returning restores them.
  const [action, setAction] = useUrlState("au_action", "");
  const [status, setStatus] = useUrlState("au_status", "");
  const [entityType, setEntityType] = useUrlState("au_entity", "");
  const [offsetStr, setOffsetStr] = useUrlState("au_offset", "0");
  const offset = Math.max(0, Number(offsetStr) || 0);

  const filters: AuditFilterValues = { action, status, entity_type: entityType };
  const params: AuditListParams = { ...filters, limit: LIMIT, offset };
  const query = useAuditLogs(params);

  function onFilterChange(patch: Partial<AuditFilterValues>) {
    if (patch.action !== undefined) setAction(patch.action);
    if (patch.status !== undefined) setStatus(patch.status);
    if (patch.entity_type !== undefined) setEntityType(patch.entity_type);
    setOffsetStr("0"); // back to first page when filters change
  }

  return (
    <>
      <div className="mb-4">
        <AuditLogFilters values={filters} onChange={onFilterChange} />
      </div>
      <AuditLogTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={(o) => setOffsetStr(String(o))}
      />
    </>
  );
}
