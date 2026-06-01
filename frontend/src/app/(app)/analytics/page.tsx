import { Suspense } from "react";

import { AnalyticsView } from "@/features/analytics/analytics-view";

export default function AnalyticsPage() {
  return (
    <Suspense>
      <AnalyticsView />
    </Suspense>
  );
}
