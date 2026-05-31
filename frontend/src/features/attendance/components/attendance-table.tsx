"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";

import { Pagination } from "@/components/data/pagination";
import { EmptyState } from "@/components/feedback/empty-state";
import { ErrorState } from "@/components/feedback/error-state";
import { TableSkeleton } from "@/components/feedback/table-skeleton";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMinutes } from "@/lib/format";

import { StatusBadge } from "./status-badge";
import { useEmployeeOptions } from "../employee-options";
import type { Attendance, AttendancePage } from "../types";

interface AttendanceTableProps {
  data: AttendancePage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
  canManage: boolean;
  onRequestDelete: (record: Attendance) => void;
  emptyAction?: React.ReactNode;
}

export function AttendanceTable({
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
  canManage,
  onRequestDelete,
  emptyAction,
}: AttendanceTableProps) {
  const router = useRouter();
  const { byId } = useEmployeeOptions();
  const cols = canManage ? 6 : 5;
  const rows = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee</TableHead>
            <TableHead>Date</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Total</TableHead>
            <TableHead>Overtime</TableHead>
            {canManage && <TableHead className="w-12 text-right">Actions</TableHead>}
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={cols} />}

        {showRows && (
          <TableBody>
            {rows.map((r) => (
              <TableRow
                key={r.id}
                className="cursor-pointer"
                onClick={() => router.push(`/attendance/${r.id}`)}
              >
                <TableCell className="font-medium">
                  {byId.get(r.employee_id) ?? "—"}
                </TableCell>
                <TableCell className="tabular text-muted-foreground">
                  {r.attendance_date}
                </TableCell>
                <TableCell>
                  <StatusBadge status={r.status} />
                </TableCell>
                <TableCell className="tabular">{formatMinutes(r.total_minutes)}</TableCell>
                <TableCell className="tabular text-muted-foreground">
                  {formatMinutes(r.overtime_minutes)}
                </TableCell>
                {canManage && (
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" aria-label="Row actions">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem asChild>
                          <Link href={`/attendance/${r.id}/edit`}>
                            <Pencil className="h-4 w-4" />
                            Edit
                          </Link>
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          onSelect={() => onRequestDelete(r)}
                          className="text-destructive focus:bg-destructive/10"
                        >
                          <Trash2 className="h-4 w-4" />
                          Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>

      {isError && <ErrorState message="Could not load attendance." onRetry={onRetry} />}
      {showEmpty && (
        <EmptyState
          title="No attendance records"
          description="No records match the current filters."
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
