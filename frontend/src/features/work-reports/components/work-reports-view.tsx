"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { useAssignableProjects } from "@/features/tasks/hooks";
import { can, isManagerial } from "@/lib/rbac";

import {
  WorkReportsFilters,
  type EmployeeFilterOption,
  type WorkReportFilterValues,
} from "./work-reports-filters";
import { WorkReportsTable } from "./work-reports-table";
import { useWorkReportList } from "../hooks";
import { WORK_REPORT_STATUSES } from "../schemas";
import type { WorkReportListParams, WorkReportStatus } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): WorkReportStatus | "" {
  return value && (WORK_REPORT_STATUSES as readonly string[]).includes(value)
    ? (value as WorkReportStatus)
    : "";
}

export function WorkReportsView({ title = "Reports" }: { title?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role, employee, employeeId } = useAuth();
  const isManager = isManagerial(role);
  // Team leads (who are `employee` role) get the same filter once they lead
  // a project — degraded back to a plain contributor, assignableProjects is
  // empty and they fall back to seeing only their own reports.
  const { data: assignableProjects } = useAssignableProjects({ enabled: !isManager });
  const isTeamLead = !isManager && (assignableProjects?.length ?? 0) > 0;
  const showEmployeeFilter = isManager || isTeamLead;
  const canCreate = can(role, "report.submit");

  const { items: orgEmployees } = useEmployeeOptions();
  const employeeOptions: EmployeeFilterOption[] = React.useMemo(() => {
    if (isManager) {
      return orgEmployees.map((e) => ({ id: e.id, label: `${e.full_name} · ${e.employee_code}` }));
    }
    if (!isTeamLead) return [];
    // Scoped to the team lead's own led-project teammates (+ themselves) —
    // not the org-wide list, which they're not RBAC-permitted to browse.
    const seen = new Map<string, string>();
    if (employeeId && employee) seen.set(employeeId, employee.full_name);
    for (const project of assignableProjects ?? []) {
      for (const member of project.members) {
        if (!seen.has(member.employee_id)) seen.set(member.employee_id, member.name);
      }
    }
    return Array.from(seen, ([id, label]) => ({ id, label }));
  }, [isManager, isTeamLead, orgEmployees, assignableProjects, employee, employeeId]);

  const params: WorkReportListParams = {
    employee_id: showEmployeeFilter ? searchParams.get("employee_id") ?? "" : "",
    project_id: searchParams.get("project_id") ?? "",
    status: parseStatus(searchParams.get("status")),
    from: searchParams.get("from") ?? "",
    to: searchParams.get("to") ?? "",
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useWorkReportList(params);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<WorkReportFilterValues>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.delete("offset");
    commit(next);
  }

  function onPageChange(offset: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    commit(next);
  }

  const items = query.data?.items ?? [];
  // Team leads see reports from their project members → show who authored each.
  const showEmployeeColumn =
    showEmployeeFilter || items.some((r) => r.employee_id !== employeeId);

  const count = query.data?.total;
  const scopeLabel = isManager
    ? "All employees"
    : showEmployeeColumn
      ? "Projects you lead"
      : undefined;
  const countLabel = count !== undefined ? `${count} ${count === 1 ? "report" : "reports"}` : undefined;
  const subtitle = [scopeLabel, countLabel].filter(Boolean).join(" · ") || undefined;

  const addButton = canCreate ? (
    <Button asChild>
      <Link href="/work-reports/new">
        <Plus className="h-4 w-4" />
        New report
      </Link>
    </Button>
  ) : null;

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={addButton}
      />
      <div className="mb-4">
        <WorkReportsFilters
          values={{
            employee_id: params.employee_id,
            project_id: params.project_id,
            status: params.status,
            from: params.from,
            to: params.to,
          }}
          showEmployee={showEmployeeFilter}
          employeeOptions={employeeOptions}
          onChange={onFilterChange}
        />
      </div>
      <WorkReportsTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        showEmployee={showEmployeeColumn}
        emptyAction={addButton}
      />
    </>
  );
}
