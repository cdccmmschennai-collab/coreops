"use client";

import * as React from "react";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDateTime } from "@/lib/format";

import { actionLabel } from "../schemas";
import type { AuditLog, AuditLogPage } from "../types";

interface AuditLogTableProps {
  data: AuditLogPage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <Badge variant={status === "failure" ? "danger" : "success"} dot>
      {status}
    </Badge>
  );
}

function entityLabel(row: AuditLog): string {
  if (!row.entity_type) return "—";
  const shortId = row.entity_id ? row.entity_id.slice(0, 8) : "";
  return shortId ? `${row.entity_type} · ${shortId}` : row.entity_type;
}

export function AuditLogTable({
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
}: AuditLogTableProps) {
  const cols = 6;
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const rows: AuditLog[] = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>When</TableHead>
            <TableHead>Actor</TableHead>
            <TableHead>Action</TableHead>
            <TableHead>Entity</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>IP</TableHead>
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={cols} />}

        {showRows && (
          <TableBody>
            {rows.map((r) => {
              const isOpen = expanded === r.id;
              const hasDetails = r.details && Object.keys(r.details).length > 0;
              return (
                <React.Fragment key={r.id}>
                  <TableRow
                    className={hasDetails ? "cursor-pointer" : undefined}
                    onClick={() => hasDetails && setExpanded(isOpen ? null : r.id)}
                  >
                    <TableCell className="tabular whitespace-nowrap text-muted-foreground">
                      {formatDateTime(r.created_at)}
                    </TableCell>
                    <TableCell className="font-medium">
                      {r.actor_email ?? <span className="text-muted-foreground">system</span>}
                    </TableCell>
                    <TableCell>{actionLabel(r.action)}</TableCell>
                    <TableCell className="text-muted-foreground">{entityLabel(r)}</TableCell>
                    <TableCell>
                      <StatusBadge status={r.status} />
                    </TableCell>
                    <TableCell className="tabular text-muted-foreground">
                      {r.ip_address ?? "—"}
                    </TableCell>
                  </TableRow>
                  {isOpen && hasDetails && (
                    <TableRow>
                      <TableCell colSpan={cols} className="bg-muted/40">
                        <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-muted-foreground">
                          {JSON.stringify(r.details, null, 2)}
                        </pre>
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              );
            })}
          </TableBody>
        )}
      </Table>

      {isError && <ErrorState message="Could not load audit log." onRetry={onRetry} />}
      {showEmpty && (
        <EmptyState
          title="No audit events"
          description="No events match the current filters."
        />
      )}
      {showRows && data && (
        <Pagination
          total={data.total}
          limit={data.limit}
          offset={data.offset}
          onPageChange={onPageChange}
        />
      )}
    </div>
  );
}
