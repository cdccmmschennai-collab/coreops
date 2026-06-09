"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { TasksFilters, type TaskFilterValues } from "./tasks-filters";
import { TasksTable } from "./tasks-table";
import { tasksApi } from "../api";
import { useTasks } from "../hooks";
import { TASK_PRIORITIES, TASK_STATUSES } from "../schemas";
import type { Task, TaskListParams, TaskPriority, TaskStatus } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): TaskStatus | "" {
  return value && (TASK_STATUSES as readonly string[]).includes(value)
    ? (value as TaskStatus)
    : "";
}

function parsePriority(value: string | null): TaskPriority | "" {
  return value && (TASK_PRIORITIES as readonly string[]).includes(value)
    ? (value as TaskPriority)
    : "";
}

export function TasksView({ mode }: { mode: "mine" | "all" }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const canManage = can(role, "task.manage");

  const params: TaskListParams = {
    mine: mode === "mine",
    q: searchParams.get("q") ?? "",
    status: parseStatus(searchParams.get("status")),
    priority: parsePriority(searchParams.get("priority")),
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useTasks(params);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<TaskFilterValues>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.delete("offset");
    commit(next);
  }

  function onPageChange(offset: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    commit(next);
  }

  async function onRequestCancel(task: Task) {
    try {
      await tasksApi.update(task.id, { status: "cancelled" });
      toast.success("Task cancelled");
      void query.refetch();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Couldn't cancel task");
    }
  }

  async function onStatusChange(task: Task, status: Task["status"]) {
    try {
      await tasksApi.updateStatus(task.id, { status });
      toast.success("Status updated");
      void query.refetch();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Couldn't update status");
    }
  }

  const addButton = canManage ? (
    <Button asChild>
      <Link href="/tasks/new">
        <Plus className="h-4 w-4" />
        New task
      </Link>
    </Button>
  ) : null;

  const count = query.data?.total;

  const pmTabs = canManage
    ? [
        { value: "/tasks", label: "My Tasks" },
        { value: "/tasks/all", label: "All Tasks", count },
      ]
    : [];

  return (
    <>
      <PageHeader
        title="Tasks"
        subtitle={
          count !== undefined
            ? `${count} ${count === 1 ? "task" : "tasks"}`
            : mode === "mine"
              ? "Work assigned to you"
              : "Team task overview"
        }
        actions={addButton}
      />

      {pmTabs.length > 0 && (
        <Tabs
          className="mb-4"
          value={mode === "all" ? "/tasks/all" : "/tasks"}
          onChange={(href) => {
            const qs = searchParams.toString();
            router.push(qs ? `${href}?${qs}` : href);
          }}
          items={pmTabs}
        />
      )}

      <div className="mb-4">
        <TasksFilters
          values={{ q: params.q, status: params.status, priority: params.priority }}
          onChange={onFilterChange}
        />
      </div>

      <TasksTable
        mode={mode}
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        canManage={canManage && mode === "all"}
        onRequestCancel={canManage ? onRequestCancel : undefined}
        onStatusChange={mode === "mine" ? onStatusChange : undefined}
        emptyAction={canManage && mode === "all" ? addButton : undefined}
      />
    </>
  );
}
