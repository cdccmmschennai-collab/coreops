import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { TasksView } from "@/features/tasks/components/tasks-view";

export default function MyTasksPage() {
  return (
    <RequireCapability capability="task.view">
      <Suspense>
        <TasksView mode="mine" />
      </Suspense>
    </RequireCapability>
  );
}
