"use client";

import { useParams } from "next/navigation";

import { RequireCapability } from "@/components/auth/require-capability";
import { EmployeeEdit } from "@/features/employees/components/employee-edit";

export default function EditEmployeePage() {
  const { id } = useParams<{ id: string }>();
  return (
    <RequireCapability capability="employee.manage">
      <EmployeeEdit id={id} />
    </RequireCapability>
  );
}
