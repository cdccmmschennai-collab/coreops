import { Suspense } from "react";

import { WorkReportsView } from "@/features/work-reports/components/work-reports-view";

export default function MyReportsPage() {
  return (
    <Suspense>
      <WorkReportsView title="Reports" />
    </Suspense>
  );
}
