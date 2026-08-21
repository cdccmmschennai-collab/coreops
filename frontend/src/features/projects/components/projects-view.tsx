"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ClipboardList, Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { ProductionStatusReportDialog } from "@/features/production-status/components/production-status-report-dialog";
import { canViewProductionStatusReport } from "@/features/production-status/production-status-report";
import { can } from "@/lib/rbac";

import { ArchiveDialog } from "./archive-dialog";
import { ProjectsFilters, type ProjectFilterValues } from "./projects-filters";
import { ProjectsTable } from "./projects-table";
import { useProjects } from "../hooks";
import { PROJECT_STATUSES } from "../schemas";
import type { Project, ProjectListParams, ProjectStatus } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): ProjectStatus | "" {
  return value && (PROJECT_STATUSES as readonly string[]).includes(value)
    ? (value as ProjectStatus)
    : "";
}

export function ProjectsView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const canManage = can(role, "project.manage");
  const isEmployee = role === "employee";
  const emptyTitle = isEmployee ? "No projects assigned" : undefined;
  const emptyDescription = isEmployee
    ? "You haven't been assigned to any projects yet. Contact your project manager."
    : undefined;

  const params: ProjectListParams = {
    q: searchParams.get("q") ?? "",
    status: parseStatus(searchParams.get("status")),
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useProjects(params);
  const [archiveTarget, setArchiveTarget] = React.useState<Project | null>(null);
  const [reportOpen, setReportOpen] = React.useState(false);

  // The cumulative Production Status report is PM-only. A Project Head and an
  // activity Lead both read Production Status on their own projects and still
  // must not see this - it spans every project. The endpoint enforces the same
  // rule, so hiding the button is convenience, not the control.
  const canViewReport = canViewProductionStatusReport(role);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<ProjectFilterValues>) {
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

  const addButton = canManage ? (
    <Button asChild>
      <Link href="/projects/new">
        <Plus className="h-4 w-4" />
        New project
      </Link>
    </Button>
  ) : null;

  // Sits beside "New project" in the page header. Secondary variant: reviewing
  // a report is not the primary action on this page, creating a project is.
  const headerActions = (
    <>
      {canViewReport && (
        <Button variant="secondary" onClick={() => setReportOpen(true)}>
          <ClipboardList className="h-4 w-4" />
          Production Status
        </Button>
      )}
      {addButton}
    </>
  );

  const count = query.data?.total;

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={
          count !== undefined ? `${count} ${count === 1 ? "project" : "projects"}` : undefined
        }
        actions={headerActions}
      />
      <div className="mb-4">
        <ProjectsFilters values={{ q: params.q, status: params.status }} onChange={onFilterChange} />
      </div>
      <ProjectsTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        canManage={canManage}
        onRequestArchive={setArchiveTarget}
        emptyAction={addButton}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      />
      <ArchiveDialog
        project={archiveTarget}
        onOpenChange={(open) => {
          if (!open) setArchiveTarget(null);
        }}
      />
      {/* Mounted only for a PM, so the report query can never be fired by a
          viewer the endpoint would refuse. */}
      {canViewReport && (
        <ProductionStatusReportDialog open={reportOpen} onOpenChange={setReportOpen} />
      )}
    </>
  );
}
