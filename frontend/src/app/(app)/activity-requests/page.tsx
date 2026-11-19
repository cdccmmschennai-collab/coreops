import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { ActivityRequestsView } from "@/features/activity-requests/components/activity-requests-view";

export default function ActivityRequestsPage() {
  // Suspense boundary: the tab and the rework filters are URL state
  // (useUrlState -> useSearchParams), which Next requires to be suspended.
  return (
    <RequireCapability capability="activity.review">
      <Suspense>
        <ActivityRequestsView />
      </Suspense>
    </RequireCapability>
  );
}