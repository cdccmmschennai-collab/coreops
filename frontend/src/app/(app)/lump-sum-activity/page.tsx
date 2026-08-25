import { Suspense } from "react";

import { LumpSumActivityView } from "@/features/continuation-requests/components/lump-sum-activity-view";

export default function LumpSumActivityPage() {
  // Suspense boundary: the panel's queue tab is URL state (useUrlState ->
  // useSearchParams), which Next requires to be suspended.
  return (
    <Suspense>
      <LumpSumActivityView />
    </Suspense>
  );
}
