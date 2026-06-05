"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
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

  const count = query.data?.total;

  return (
    <>
      <PageHeader
        title="Projects"
        subtitle={
          count !== undefined ? `${count} ${count === 1 ? "project" : "projects"}` : undefined
        }
        actions={addButton}
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
    </>
  );
}
