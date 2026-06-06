"use client";

import Link from "next/link";

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
import { formatDateTime } from "@/lib/format";

import { RoleBadge } from "./role-badge";
import { UserStatusBadge } from "./user-status-badge";
import type { UserListItem, UserPage } from "../types";

interface UsersTableProps {
  data: UserPage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
}

export function UsersTable({
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
}: UsersTableProps) {
  const cols = 6;
  const rows: UserListItem[] = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Employee Name</TableHead>
            <TableHead>Employee ID</TableHead>
            <TableHead>Login Email</TableHead>
            <TableHead>Role</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Last Login</TableHead>
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={cols} />}

        {showRows && (
          <TableBody>
            {rows.map((u) => (
              <TableRow key={u.id}>
                <TableCell className="font-medium">
                  {u.linked_employee ? (
                    <Link
                      href={`/employees/${u.linked_employee.id}`}
                      className="text-primary hover:underline"
                    >
                      {u.linked_employee.full_name}
                    </Link>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="tabular text-muted-foreground">
                  {u.linked_employee?.employee_code ?? "—"}
                </TableCell>
                <TableCell>{u.email}</TableCell>
                <TableCell>
                  <RoleBadge role={u.role} />
                </TableCell>
                <TableCell>
                  <UserStatusBadge active={u.is_active} />
                </TableCell>
                <TableCell className="tabular text-muted-foreground">
                  {formatDateTime(u.last_login_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>

      {isError && <ErrorState message="Could not load users." onRetry={onRetry} />}
      {showEmpty && (
        <EmptyState
          title="No users"
          description="No users match the current filters."
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
