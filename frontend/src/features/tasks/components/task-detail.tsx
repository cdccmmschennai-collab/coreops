"use client";

import * as React from "react";
import Link from "next/link";
import { Check, Pencil, XCircle } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { formatDateTime } from "@/lib/format";
import { can } from "@/lib/rbac";

import { PriorityBadge, StatusBadge } from "./status-badge";
import { useTask, useUpdateTask, useUpdateTaskStatus } from "../hooks";
import { EMPLOYEE_TASK_STATUSES, TASK_STATUS_LABEL } from "../schemas";
import type { Task, TaskStatus } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value ?? "—"}</span>
    </div>
  );
}

function formatDueDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso.includes("T") ? iso : `${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString([], { year: "numeric", month: "long", day: "numeric" });
}

export function TaskDetail({ id }: { id: string }) {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "task.manage");

  const query = useTask(id);
  const task = query.data;
  const updateTask = useUpdateTask(id);
  const updateStatus = useUpdateTaskStatus(id);

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-56 max-w-2xl" />
      </>
    );
  }

  if (query.isError || !task) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Task not found" : "Couldn't load task"}
        message={
          notFound
            ? "This task may have been removed, or you don't have access to it."
            : "Please try again."
        }
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const isAssignee = employeeId === task.assigned_to_employee_id;
  const isActive = task.status !== "cancelled" && task.status !== "completed";

  async function handleCancel() {
    try {
      await updateTask.mutateAsync({ status: "cancelled" });
      toast.success("Task cancelled");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Couldn't cancel task");
    }
  }

  async function handleStatusChange(status: TaskStatus) {
    try {
      await updateStatus.mutateAsync({ status });
      toast.success(`Marked as ${TASK_STATUS_LABEL[status].toLowerCase()}`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Couldn't update status");
    }
  }

  const actions = (
    <>
      {canManage && isActive && (
        <>
          <Button variant="secondary" asChild>
            <Link href={`/tasks/${id}/edit`}>
              <Pencil className="h-4 w-4" />
              Edit
            </Link>
          </Button>
          <Button
            variant="secondary"
            onClick={() => void handleCancel()}
            disabled={updateTask.isPending}
          >
            <XCircle className="h-4 w-4" />
            Cancel task
          </Button>
        </>
      )}
      {isAssignee && isActive && (
        <StatusActions task={task} onChange={(s) => void handleStatusChange(s)} />
      )}
    </>
  );

  return (
    <>
      <Link href="/tasks" className="text-sm text-primary hover:underline">
        ← Tasks
      </Link>
      <PageHeader
        className="mt-2"
        title={task.title}
        subtitle="Task details"
        actions={actions}
      />
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          {task.description && (
            <p className="pb-4 text-sm text-muted-foreground">{task.description}</p>
          )}
          <div>
            <Row label="Status" value={<StatusBadge status={task.status} />} />
            <Row label="Priority" value={<PriorityBadge priority={task.priority} />} />
            <Row label="Assignee" value={task.assigned_to_name || "—"} />
            <Row label="Assigned by" value={task.assigned_by_name || "—"} />
            <Row label="Due date" value={formatDueDate(task.due_date)} />
            <Row label="Created" value={formatDateTime(task.created_at)} />
            <Row label="Updated" value={formatDateTime(task.updated_at)} />
          </div>
        </CardContent>
      </Card>
    </>
  );
}

function StatusActions({
  task,
  onChange,
}: {
  task: Task;
  onChange: (status: TaskStatus) => void;
}) {
  const options = EMPLOYEE_TASK_STATUSES.filter((s) => s !== task.status);
  if (options.length === 0) return null;

  return (
    <>
      {options.map((status) => (
        <Button key={status} onClick={() => onChange(status)}>
          {status === "completed" ? (
            <Check className="h-4 w-4" />
          ) : null}
          {status === "in_progress"
            ? "Start"
            : status === "completed"
              ? "Complete"
              : "Reopen"}
        </Button>
      ))}
    </>
  );
}
