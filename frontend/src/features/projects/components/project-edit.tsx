"use client";

import Link from "next/link";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { AppError } from "@/lib/api-client";

import { ProjectForm } from "./project-form";
import { useProject } from "../hooks";
import type { ProjectFormValues } from "../schemas";

export function ProjectEdit({ id }: { id: string }) {
  const query = useProject(id);
  const project = query.data;

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-96" />
      </>
    );
  }

  if (query.isError || !project) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Project not found" : "Couldn't load project"}
        message={notFound ? "This project may have been archived." : "Please try again."}
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const defaults: ProjectFormValues = {
    code: project.code,
    name: project.name,
    job_code: project.job_code_code ?? "",
    client: project.client ?? "",
    description: project.description ?? "",
    status: project.status,
    start_date: project.start_date ?? "",
    planned_completion_date: project.planned_completion_date ?? "",
    actual_completion_date: project.actual_completion_date ?? "",
  };

  return (
    <>
      <Link href={`/projects/${project.id}`} className="text-sm text-primary hover:underline">
        ← {project.name}
      </Link>
      <PageHeader className="mt-2" title={`Edit ${project.name}`} subtitle={project.code} />
      <ProjectForm mode="edit" projectId={project.id} defaultValues={defaults} />
    </>
  );
}
