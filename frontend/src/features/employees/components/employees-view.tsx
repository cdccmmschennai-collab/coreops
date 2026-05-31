"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";

import { DeactivateDialog } from "./deactivate-dialog";
import { EmployeesFilters, type EmployeeFilterValues } from "./employees-filters";
import { EmployeesTable } from "./employees-table";
import { useEmployees } from "../hooks";
import { EMPLOYEE_STATUSES } from "../schemas";
import type { Employee, EmployeeListParams, EmployeeStatus } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): EmployeeStatus | "" {
  return value && (EMPLOYEE_STATUSES as readonly string[]).includes(value)
    ? (value as EmployeeStatus)
    : "";
}

export function EmployeesView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const canManage = can(role, "employee.manage");

  const params: EmployeeListParams = {
    q: searchParams.get("q") ?? "",
    department: searchParams.get("department") ?? "",
    status: parseStatus(searchParams.get("status")),
    manager_id: "",
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useEmployees(params);
  const [deactivateTarget, setDeactivateTarget] = React.useState<Employee | null>(null);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<EmployeeFilterValues>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.delete("offset"); // back to first page when filters change
    commit(next);
  }

  function onPageChange(offset: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    commit(next);
  }

  const addButton = canManage ? (
    <Button asChild>
      <Link href="/employees/new">
        <Plus className="h-4 w-4" />
        Add employee
      </Link>
    </Button>
  ) : null;

  const count = query.data?.total;

  return (
    <>
      <PageHeader
        title="Employees"
        subtitle={
          count !== undefined ? `${count} ${count === 1 ? "person" : "people"}` : undefined
        }
        actions={addButton}
      />
      <div className="mb-4">
        <EmployeesFilters
          values={{ q: params.q, department: params.department, status: params.status }}
          onChange={onFilterChange}
        />
      </div>
      <EmployeesTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        canManage={canManage}
        onRequestDeactivate={setDeactivateTarget}
        emptyAction={addButton}
      />
      <DeactivateDialog
        employee={deactivateTarget}
        onOpenChange={(open) => {
          if (!open) setDeactivateTarget(null);
        }}
      />
    </>
  );
}
