"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, Pencil } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs } from "@/components/ui/tabs";
import { useAuth } from "@/features/auth/auth-provider";
import { DeliverablesTab } from "@/features/project-deliverables/components/deliverables-tab";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { ArchiveDialog } from "./archive-dialog";
import { ProjectMembers } from "./project-members";
import { StatusBadge } from "./status-badge";
import { useProject } from "../hooks";
import type { Project } from "../types";

const TAB_ITEMS = [
  { value: "overview", label: "Overview" },
  { value: "deliverables", label: "Deliverables" },
];

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export function ProjectDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role } = useAuth();
  const canManage = can(role, "project.manage");

  const query = useProject(id);
  const project = query.data;
  const [confirm, setConfirm] = React.useState<Project | null>(null);
  const [activeTab, setActiveTab] = React.useState("overview");

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </div>
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

  const archived = project.status === "archived";
  const subtitleParts = [project.code, project.client].filter(Boolean) as string[];

  return (
    <>
      <Link href="/projects/list" className="text-sm text-primary hover:underline">
        ← Projects
      </Link>
      <PageHeader
        className="mt-2"
        title={project.name}
        subtitle={subtitleParts.join(" · ")}
        actions={
          canManage ? (
            <>
              <Button variant="secondary" asChild>
                <Link href={`/projects/${project.id}/edit`}>
                  <Pencil className="h-4 w-4" />
                  Edit
                </Link>
              </Button>
              <Button variant="danger" onClick={() => setConfirm(project)}>
                <Archive className="h-4 w-4" />
                Archive
              </Button>
            </>
          ) : null
        }
      />

      <Tabs
        items={TAB_ITEMS}
        value={activeTab}
        onChange={setActiveTab}
        className="mb-4"
      />

      {activeTab === "overview" && (
        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Overview</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row label="Code" value={<span className="font-mono">{project.code}</span>} />
              <Row
                label="Job Code"
                value={
                  project.job_code_code ? (
                    <span className="font-mono">{project.job_code_code}</span>
                  ) : (
                    "—"
                  )
                }
              />
              <Row label="Project Name" value={project.client ?? "—"} />
              <Row label="Status" value={<StatusBadge status={project.status} />} />
              <Row label="Start date" value={project.start_date ?? "—"} />
              <Row label="End date" value={project.end_date ?? "—"} />
              {project.description && (
                <div className="py-2 text-sm">
                  <div className="mb-1 text-muted-foreground">Description</div>
                  <p className="whitespace-pre-wrap">{project.description}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <ProjectMembers project={project} />
        </div>
      )}

      {activeTab === "deliverables" && (
        <DeliverablesTab projectId={project.id} projectArchived={archived} />
      )}

      <ArchiveDialog
        project={confirm}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        onDone={() => router.push("/projects/list")}
      />
    </>
  );
}
