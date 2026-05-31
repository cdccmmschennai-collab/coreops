"use client";

import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { EmployeeForm } from "@/features/employees/components/employee-form";
import { EMPTY_EMPLOYEE_FORM } from "@/features/employees/schemas";

export default function NewEmployeePage() {
  return (
    <RequireCapability capability="employee.manage">
      <Link href="/employees" className="text-sm text-primary hover:underline">
        ← Employees
      </Link>
      <PageHeader className="mt-2" title="New employee" subtitle="Create a workforce record." />
      <EmployeeForm mode="create" defaultValues={EMPTY_EMPLOYEE_FORM} />
    </RequireCapability>
  );
}
