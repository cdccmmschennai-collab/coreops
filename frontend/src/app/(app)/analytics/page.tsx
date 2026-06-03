import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { AnalyticsView } from "@/features/analytics/analytics-view";

export default function AnalyticsPage() {
  return (
    <RequireCapability capability="analytics.view">
      <Suspense>
        <AnalyticsView />
      </Suspense>
    </RequireCapability>
  );
}
