import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { TasksView } from "@/features/tasks/components/tasks-view";

// Reachable by anyone with task.view — TasksView itself decides whether the
// viewer is allowed an "All Tasks" mode (PM or team lead) and falls back to
// "My Tasks" otherwise, same as /tasks.
export default function AllTasksPage() {
  return (
    <RequireCapability capability="task.view">
      <Suspense>
        <TasksView routeMode="all" />
      </Suspense>
    </RequireCapability>
  );
}
