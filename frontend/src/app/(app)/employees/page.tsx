import { Suspense } from "react";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmployeesView } from "@/features/employees/components/employees-view";

export default function EmployeesPage() {
  return (
    <RequireCapability capability="employee.view">
      <Suspense>
        <EmployeesView />
      </Suspense>
    </RequireCapability>
  );
}
