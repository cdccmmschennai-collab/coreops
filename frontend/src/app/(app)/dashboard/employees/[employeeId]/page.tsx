"use client";

import { Suspense } from "react";
import { useParams } from "next/navigation";

import { EmployeeDetailPage } from "@/features/employee-performance/components/employee-detail-page";

export default function Page() {
  const { employeeId } = useParams<{ employeeId: string }>();
  return (
    <Suspense>
      <EmployeeDetailPage employeeId={employeeId} />
    </Suspense>
  );
}
