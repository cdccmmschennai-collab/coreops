"use client";

import * as React from "react";

import { AuditLogFilters, type AuditFilterValues } from "./audit-log-filters";
import { AuditLogTable } from "./audit-log-table";
import { useAuditLogs } from "../hooks";
import type { AuditListParams } from "../types";

const LIMIT = 20;

export function AuditLogView() {
  const [filters, setFilters] = React.useState<AuditFilterValues>({
    action: "",
    status: "",
    entity_type: "",
  });
  const [offset, setOffset] = React.useState(0);

  const params: AuditListParams = { ...filters, limit: LIMIT, offset };
  const query = useAuditLogs(params);

  function onFilterChange(patch: Partial<AuditFilterValues>) {
    setFilters((prev) => ({ ...prev, ...patch }));
    setOffset(0); // back to first page when filters change
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
        onPageChange={setOffset}
      />
    </>
  );
}
