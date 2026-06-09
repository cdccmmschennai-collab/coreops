import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { TaskForm } from "@/features/tasks/components/task-form";

export default function NewTaskPage() {
  return (
    <RequireCapability capability="task.manage">
      <PageHeader title="New task" subtitle="Assign work to a team member" />
      <TaskForm mode="create" />
    </RequireCapability>
  );
}
