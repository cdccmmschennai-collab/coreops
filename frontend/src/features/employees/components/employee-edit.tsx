"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import { EmployeeForm } from "./employee-form";
import { useEmployee } from "../hooks";
import type { EmployeeFormValues } from "../schemas";

export function EmployeeEdit({ id }: { id: string }) {
  const query = useEmployee(id);
  const emp = query.data;

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-96" />
      </>
    );
  }

  if (query.isError || !emp) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Employee not found" : "Couldn't load employee"}
        message={notFound ? "This employee may have been deactivated." : "Please try again."}
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const defaults: EmployeeFormValues = {
    employee_code: emp.employee_code,
    first_name: emp.first_name,
    last_name: emp.last_name,
    work_email: emp.work_email ?? "",
    phone: emp.phone ?? "",
    department: emp.department ?? "",
    designation: emp.designation ?? "",
    date_of_joining: emp.date_of_joining ?? "",
    status: emp.status,
    manager_id: emp.manager_id ?? "",
    user_id: emp.user_id ?? "",
  };

  return (
    <>
      <Link href={`/employees/${emp.id}`} className="text-sm text-primary hover:underline">
        ← {emp.full_name}
      </Link>
      <PageHeader className="mt-2" title={`Edit ${emp.full_name}`} subtitle={emp.employee_code} />
      <EmployeeForm mode="edit" employeeId={emp.id} defaultValues={defaults} />
    </>
  );
}
