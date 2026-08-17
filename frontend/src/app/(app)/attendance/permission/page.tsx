"use client";

import * as React from "react";

import { PermissionHistory } from "@/features/permissions/components/permission-history";

/** The signed-in user's own permission history, reached by clicking the
 *  Permission Remaining KPI card on /attendance. Not in the sidebar - it is a
 *  destination, not a navigation item.
 *
 *  Suspense boundary: the selected month lives in the URL via `useUrlState`,
 *  which reads `useSearchParams`. */
export default function PermissionHistoryPage() {
  return (
    <React.Suspense fallback={null}>
      <PermissionHistory />
    </React.Suspense>
  );
}
