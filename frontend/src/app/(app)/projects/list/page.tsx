import { Suspense } from "react";
import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { ProjectsView } from "@/features/projects/components/projects-view";

export default function ProjectsListPage() {
  return (
    <RequireCapability capability="project.view">
      <Link href="/projects" className="text-sm text-primary hover:underline">
        ← Back
      </Link>
      <Suspense>
        <ProjectsView />
      </Suspense>
    </RequireCapability>
  );
}
