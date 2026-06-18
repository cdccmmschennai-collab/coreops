import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { TasksView } from "@/features/tasks/components/tasks-view";

export default function AllTasksPage() {
  return (
    <RequireCapability capability="task.manage">
      <Suspense>
        <TasksView mode="all" />
      </Suspense>
    </RequireCapability>
  );
}
