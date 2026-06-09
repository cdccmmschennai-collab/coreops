"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { MoreHorizontal, Pencil, XCircle } from "lucide-react";

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

import { PriorityBadge, StatusBadge } from "./status-badge";
import type { Task, TaskPage } from "../types";

function formatDueDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.includes("T") ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
}

interface TasksTableProps {
  mode: "mine" | "all";
  data: TaskPage | undefined;
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onPageChange: (offset: number) => void;
  canManage: boolean;
  currentEmployeeId?: string | null;
  onRequestCancel?: (task: Task) => void;
  onStatusChange?: (task: Task, status: Task["status"]) => void;
  emptyAction?: React.ReactNode;
}

export function TasksTable({
  mode,
  data,
  isLoading,
  isError,
  onRetry,
  onPageChange,
  canManage,
  currentEmployeeId,
  onRequestCancel,
  onStatusChange,
  emptyAction,
}: TasksTableProps) {
  const router = useRouter();
  const rows = data?.items ?? [];
  const showRows = !isLoading && !isError && rows.length > 0;
  const showEmpty = !isLoading && !isError && rows.length === 0;
  const cols = mode === "all" ? (canManage ? 6 : 5) : canManage ? 6 : 5;

  if (isError) {
    return <ErrorState title="Couldn't load tasks" onRetry={onRetry} />;
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Task</TableHead>
            {mode === "all" && <TableHead>Assignee</TableHead>}
            {mode === "mine" && <TableHead>Assigned by</TableHead>}
            <TableHead>Priority</TableHead>
            <TableHead>Due date</TableHead>
            <TableHead>Status</TableHead>
            {(canManage || onStatusChange) && (
              <TableHead className="w-12 text-right">Actions</TableHead>
            )}
          </TableRow>
        </TableHeader>

        {isLoading && <TableSkeleton cols={cols} />}

        {showRows && (
          <TableBody>
            {rows.map((task) => (
              <TableRow
                key={task.id}
                className="cursor-pointer"
                onClick={() => router.push(`/tasks/${task.id}`)}
              >
                <TableCell className="font-medium">{task.title}</TableCell>
                {mode === "all" && (
                  <TableCell>{task.assigned_to_name || "—"}</TableCell>
                )}
                {mode === "mine" && (
                  <TableCell>{task.assigned_by_name || "—"}</TableCell>
                )}
                <TableCell>
                  <PriorityBadge priority={task.priority} />
                </TableCell>
                <TableCell>{formatDueDate(task.due_date)}</TableCell>
                <TableCell>
                  <StatusBadge status={task.status} />
                </TableCell>
                {(canManage || onStatusChange) && (
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                    <RowActions
                      task={task}
                      canManage={canManage}
                      isAssignee={task.assigned_to_employee_id === currentEmployeeId}
                      onRequestCancel={onRequestCancel}
                      onStatusChange={onStatusChange}
                    />
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        )}
      </Table>

      {showEmpty && (
        <EmptyState
          title={mode === "mine" ? "No tasks assigned to you" : "No tasks yet"}
          description={
            mode === "mine"
              ? "When a project manager assigns you a task, it will appear here."
              : "Create a task and assign it to a team member."
          }
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

function RowActions({
  task,
  canManage,
  isAssignee,
  onRequestCancel,
  onStatusChange,
}: {
  task: Task;
  canManage: boolean;
  isAssignee: boolean;
  onRequestCancel?: (task: Task) => void;
  onStatusChange?: (task: Task, status: Task["status"]) => void;
}) {
  const isActive = task.status !== "cancelled" && task.status !== "completed";

  if (canManage) {
    return (
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem asChild>
            <Link href={`/tasks/${task.id}/edit`}>
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </Link>
          </DropdownMenuItem>
          {isActive && onRequestCancel && (
            <DropdownMenuItem
              className="text-destructive focus:text-destructive"
              onClick={() => onRequestCancel(task)}
            >
              <XCircle className="mr-2 h-4 w-4" />
              Cancel task
            </DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }

  if (!onStatusChange || !isActive || !isAssignee) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {task.status !== "open" && (
          <DropdownMenuItem onClick={() => onStatusChange(task, "open")}>
            Mark open
          </DropdownMenuItem>
        )}
        {task.status !== "in_progress" && (
          <DropdownMenuItem onClick={() => onStatusChange(task, "in_progress")}>
            In progress
          </DropdownMenuItem>
        )}
        {task.status !== "completed" && (
          <DropdownMenuItem onClick={() => onStatusChange(task, "completed")}>
            Completed
          </DropdownMenuItem>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
