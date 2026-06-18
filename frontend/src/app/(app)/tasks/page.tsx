import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { TasksView } from "@/features/tasks/components/tasks-view";

export default function TasksPage() {
  return (
    <RequireCapability capability="task.view">
      <Suspense>
        <TasksView routeMode="mine" />
      </Suspense>
    </RequireCapability>
  );
}
