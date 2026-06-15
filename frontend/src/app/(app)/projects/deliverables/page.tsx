import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { AllDeliverablesView } from "@/features/project-deliverables/components/all-deliverables-view";

export default function AllDeliverablesPage() {
  return (
    <RequireCapability capability="project.view">
      <Suspense>
        <AllDeliverablesView />
      </Suspense>
    </RequireCapability>
  );
}
