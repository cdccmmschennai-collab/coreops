import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { ProjectsView } from "@/features/projects/components/projects-view";

export default function ProjectsPage() {
  return (
    <RequireCapability capability="project.view">
      <Suspense>
        <ProjectsView />
      </Suspense>
    </RequireCapability>
  );
}
