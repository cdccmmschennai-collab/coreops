"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { TaskForm } from "@/features/tasks/components/task-form";
import { useAssignableProjects } from "@/features/tasks/hooks";
import { can } from "@/lib/rbac";

export default function NewTaskPage() {
  const { role } = useAuth();
  const canManage = can(role, "task.manage");
  // Non-PMs may assign only if they lead at least one project.
  const assignable = useAssignableProjects({ enabled: !canManage });
  const allowed = canManage || (assignable.data?.length ?? 0) > 0;

  if (!canManage && assignable.isLoading) {
    return <Skeleton className="h-64 max-w-2xl" />;
  }

  if (!allowed) {
    return (
      <ErrorState
        title="Not allowed"
        message="You don't have permission to assign tasks."
      />
    );
  }

  return (
    <>
      <Link href="/tasks" className="text-sm text-primary hover:underline">
        ← Tasks
      </Link>
      <PageHeader className="mt-2" title="New task" subtitle="Assign work to a team member" />
      <TaskForm mode="create" />
    </>
  );
}
