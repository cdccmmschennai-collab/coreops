"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { BenchmarkGuideButton } from "@/features/benchmark-guide/components/benchmark-guide-button";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { can, isManagerial } from "@/lib/rbac";

import {
  WorkReportsFilters,
  type EmployeeFilterOption,
  type WorkReportFilterValues,
} from "./work-reports-filters";
import { WorkReportsTable } from "./work-reports-table";
import { useReportScope, useWorkReportList } from "../hooks";
import { WORK_REPORT_STATUSES } from "../schemas";
import type { WorkReportListParams, WorkReportStatusFilter } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): WorkReportStatusFilter | "" {
  return value && (WORK_REPORT_STATUSES as readonly string[]).includes(value)
    ? (value as WorkReportStatusFilter)
    : "";
}

export function WorkReportsView({ title = "Reports" }: { title?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role, employee, employeeId } = useAuth();
  const isManager = isManagerial(role);
  // Report scope for `employee`-role users: Project Heads get their headed
  // projects (whole-project access), Activity Leads the exact activities they
  // lead per project. A user with neither gets an empty scope and falls back
  // to seeing only their own reports, like any contributor. Informational
  // only — the backend enforces the same scope on every report endpoint.
  const { data: scope } = useReportScope({ enabled: !isManager });
  const isProjectHead = !isManager && scope?.is_project_head === true;
  const isActivityLead = !isManager && scope?.is_activity_lead === true;
  const showEmployeeFilter = isManager || isProjectHead || isActivityLead;
  const canCreate = can(role, "report.submit");

  const { items: orgEmployees } = useEmployeeOptions();
  const employeeOptions: EmployeeFilterOption[] = React.useMemo(() => {
    if (isManager) {
      return orgEmployees.map((e) => ({ id: e.id, label: `${e.full_name} · ${e.employee_code}` }));
    }
    if (!isProjectHead && !isActivityLead) return [];
    // Scoped to the members of the viewer's headed/led projects (+ themselves)
    // — not the org-wide list, which they're not RBAC-permitted to browse.
    // Employees appearing in several projects are deduplicated by id.
    const seen = new Map<string, string>();
    for (const project of scope?.projects ?? []) {
      for (const member of project.members) {
        if (!seen.has(member.employee_id)) {
          seen.set(member.employee_id, `${member.name} · ${member.employee_code}`);
        }
      }
    }
    if (employeeId && employee && !seen.has(employeeId)) {
      seen.set(employeeId, employee.full_name);
    }
    return Array.from(seen, ([id, label]) => ({ id, label }));
  }, [isManager, isProjectHead, isActivityLead, orgEmployees, scope, employee, employeeId]);

  // Heads/Leads: restrict the project filter to their report scope; other
  // roles keep the default RBAC-scoped project list.
  const scopeProjectOptions = React.useMemo(() => {
    if (isManager || !(isProjectHead || isActivityLead)) return undefined;
    return (scope?.projects ?? []).map((p) => ({
      id: p.project_id,
      label: `${p.name} · ${p.code}`,
    }));
  }, [isManager, isProjectHead, isActivityLead, scope]);

  // "Activities you lead" — shown so a Lead knows exactly which activity rows
  // their report scope covers (Head-access projects are whole-project).
  const ledActivityLabels = React.useMemo(() => {
    if (!isActivityLead) return [];
    return (scope?.projects ?? [])
      .filter((p) => p.access === "lead")
      .flatMap((p) => p.activities.map((a) => `${a.name ?? "-"} (${p.code})`));
  }, [isActivityLead, scope]);

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
  // A Head sees reports from their project members → show who authored each.
  const showEmployeeColumn =
    showEmployeeFilter || items.some((r) => r.employee_id !== employeeId);

  const count = query.data?.total;
  const scopeLabel = isManager
    ? "All employees"
    : isProjectHead && isActivityLead
      ? "Projects you head · Activities you lead"
      : isProjectHead
        ? "Projects you head"
        : isActivityLead
          ? "Activities you lead"
          : undefined;
  const countLabel = count !== undefined ? `${count} ${count === 1 ? "report" : "reports"}` : undefined;
  const subtitle = [scopeLabel, countLabel].filter(Boolean).join(" · ") || undefined;

  const newReportButton = canCreate ? (
    <Button asChild>
      <Link href="/work-reports/new">
        <Plus className="h-4 w-4" />
        New report
      </Link>
    </Button>
  ) : null;

  // Order: [ Benchmark Guide ] [ + New report ] — New report stays the primary
  // action; the guide sits to its left as a secondary button.
  const headerActions = (
    <div className="flex items-center gap-2">
      <BenchmarkGuideButton />
      {newReportButton}
    </div>
  );

  return (
    <>
      <PageHeader
        title={title}
        subtitle={subtitle}
        actions={headerActions}
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
          projectOptions={scopeProjectOptions}
          onChange={onFilterChange}
        />
        {ledActivityLabels.length > 0 && (
          <p className="mt-2 text-sm text-muted-foreground">
            Activities you lead: {ledActivityLabels.join(", ")}. Other
            employees&apos; reports show only these activities.
          </p>
        )}
      </div>
      <WorkReportsTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        showEmployee={showEmployeeColumn}
        emptyAction={newReportButton}
      />
    </>
  );
}
