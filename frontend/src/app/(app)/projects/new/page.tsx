"use client";

import Link from "next/link";

import { RequireCapability } from "@/components/auth/require-capability";
import { PageHeader } from "@/components/shell/page-header";
import { ProjectForm } from "@/features/projects/components/project-form";
import { EMPTY_PROJECT_FORM } from "@/features/projects/schemas";

export default function NewProjectPage() {
  return (
    <RequireCapability capability="project.manage">
      <Link href="/projects/list" className="text-sm text-primary hover:underline">
        ← Projects
      </Link>
      <PageHeader className="mt-2" title="New project" subtitle="Create a project record." />
      <ProjectForm mode="create" defaultValues={EMPTY_PROJECT_FORM} />
    </RequireCapability>
  );
}
