"use client";

import { useRouter } from "next/navigation";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

import { StatusBadge } from "./status-badge";
import type { Project, ProjectPage } from "../types";

interface ProjectsTableProps {
  data: ProjectPage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
  canManage: boolean;
  onRequestArchive: (project: Project) => void;
  emptyAction?: React.ReactNode;
  emptyTitle?: string;
  emptyDescription?: string;
}

export function ProjectsTable({
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
  emptyAction,
  emptyTitle,
  emptyDescription,
}: ProjectsTableProps) {
  const router = useRouter();
  const rows = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Project</TableHead>
            <TableHead>Project Name</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Members</TableHead>
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={4} />}

        {showRows && (
          <TableBody>
            {rows.map((p) => (
              <TableRow
                key={p.id}
                className="cursor-pointer"
                onClick={() => router.push(`/projects/${p.id}`)}
              >
                <TableCell>
                  <div className="font-medium">{p.name}</div>
                  <div className="font-mono text-xs text-muted-foreground">{p.code}</div>
                </TableCell>
                <TableCell className="text-muted-foreground">{p.client ?? "—"}</TableCell>
                <TableCell>
                  <StatusBadge status={p.status} />
                </TableCell>
                <TableCell className="tabular text-muted-foreground">
                  {p.member_count}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>

      {isError && <ErrorState message="Could not load projects." onRetry={onRetry} />}
      {showEmpty && (
        <EmptyState
          title={emptyTitle ?? "No projects found"}
          description={emptyDescription ?? "No projects match the current filters."}
          action={emptyAction}
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
