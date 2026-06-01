"use client";

import { useParams } from "next/navigation";

import { WorkReportDetail } from "@/features/work-reports/components/work-report-detail";

export default function WorkReportDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <WorkReportDetail id={id} />;
}
