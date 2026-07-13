"use client";

import { Suspense } from "react";

import { PmActivityReportView } from "@/features/reports-export/components/pm-activity-report-view";
import { WorkReportsView } from "@/features/work-reports/components/work-reports-view";
import { useAuth } from "@/features/auth/auth-provider";
import { isManagerial } from "@/lib/rbac";

export default function ReportsPage() {
  const { role } = useAuth();

  // PMs get the Weekly Activity Report (preview + Excel export). Team leads /
  // employees keep the existing report list — submission workflow untouched.
  if (isManagerial(role)) {
    return (
      <Suspense>
        <PmActivityReportView />
      </Suspense>
    );
  }
  return (
    <Suspense>
      <WorkReportsView title="Reports" />
    </Suspense>
  );
}
