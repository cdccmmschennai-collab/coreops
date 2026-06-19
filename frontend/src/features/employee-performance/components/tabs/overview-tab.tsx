"use client";

import { EmployeeOverview } from "../employee-overview";

// Layer 3, tab 1 — renders the SAME shared component as the Layer 2 drawer.
export function OverviewTab({ employeeId }: { employeeId: string }) {
  return <EmployeeOverview employeeId={employeeId} />;
}
