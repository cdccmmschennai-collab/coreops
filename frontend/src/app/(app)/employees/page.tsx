import { Suspense } from "react";

import { EmployeesView } from "@/features/employees/components/employees-view";

export default function EmployeesPage() {
  return (
    <Suspense>
      <EmployeesView />
    </Suspense>
  );
}
