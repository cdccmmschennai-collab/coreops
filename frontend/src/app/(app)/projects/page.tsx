import { Suspense } from "react";

import { ProjectsView } from "@/features/projects/components/projects-view";

export default function ProjectsPage() {
  return (
    <Suspense>
      <ProjectsView />
    </Suspense>
  );
}
