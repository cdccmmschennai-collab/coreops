import { Suspense } from "react";

import { WorkReportsView } from "@/features/work-reports/components/work-reports-view";

export default function WorkReportsPage() {
  return (
    <Suspense>
      <WorkReportsView />
    </Suspense>
  );
}
