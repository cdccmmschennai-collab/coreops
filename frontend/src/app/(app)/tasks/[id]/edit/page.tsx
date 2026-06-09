"use client";

import { RequireCapability } from "@/components/auth/require-capability";
import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { TaskForm } from "@/features/tasks/components/task-form";
import { useTask } from "@/features/tasks/hooks";
import type { TaskFormValues } from "@/features/tasks/schemas";

function toFormValues(task: {
  title: string;
  description: string | null;
  assigned_to_employee_id: string;
  priority: TaskFormValues["priority"];
  due_date: string | null;
}): TaskFormValues {
  return {
    title: task.title,
    description: task.description ?? "",
    assigned_to_employee_id: task.assigned_to_employee_id,
    priority: task.priority,
    due_date: task.due_date ?? "",
  };
}

function EditTaskBody({ id }: { id: string }) {
  const query = useTask(id);

  if (query.isLoading) {
    return <Skeleton className="h-96 max-w-2xl" />;
  }

  if (query.isError || !query.data) {
    return (
      <ErrorState
        title="Couldn't load task"
        onRetry={() => void query.refetch()}
      />
    );
  }

  return (
    <>
      <PageHeader title="Edit task" subtitle={query.data.title} />
      <TaskForm mode="edit" taskId={id} defaultValues={toFormValues(query.data)} />
    </>
  );
}

export default function EditTaskPage({ params }: { params: { id: string } }) {
  return (
    <RequireCapability capability="task.manage">
      <EditTaskBody id={params.id} />
    </RequireCapability>
  );
}
