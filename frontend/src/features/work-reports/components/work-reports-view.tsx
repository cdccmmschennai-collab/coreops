"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { can, isManagerial } from "@/lib/rbac";

import {
  WorkReportsFilters,
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

function roleSubtitle(role: ReturnType<typeof useAuth>["role"]): string | undefined {
  if (role === "admin") return "All employees";
  if (role === "manager") return "Your team";
  return undefined;
}

export function WorkReportsView({ title = "Reports" }: { title?: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const showEmployee = isManagerial(role);
  const canCreate = can(role, "report.submit");

  const params: WorkReportListParams = {
    employee_id: showEmployee ? searchParams.get("employee_id") ?? "" : "",
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

  const count = query.data?.total;
  const scopeLabel = roleSubtitle(role);
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
          showEmployee={showEmployee}
          onChange={onFilterChange}
        />
      </div>
      <WorkReportsTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        showEmployee={showEmployee}
        emptyAction={addButton}
      />
    </>
  );
}
