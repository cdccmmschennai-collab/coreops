"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { WorkReportEdit } from "@/features/work-reports/components/work-report-edit";

export default function EditWorkReportPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="report.submit">
      <WorkReportEdit id={id} />
    </RequireCapability>
  );
}
