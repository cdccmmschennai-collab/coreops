"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Archive, CalendarClock, ChevronDown, ChevronUp, Pencil } from "lucide-react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";
import { useUrlState } from "@/lib/use-url-state";

import { Tabs } from "@/components/ui/tabs";
import { ActivitiesTab } from "@/features/project-activities/components/activities-tab";
import { SubmissionsTab } from "@/features/project-submissions/components/submissions-tab";
import { ArchiveDialog } from "./archive-dialog";
import { ProjectMembers } from "./project-members";
import { ProjectTimeline } from "./project-timeline";
import { StatusBadge } from "./status-badge";
import { useProject, usePlannedDateChanges, useUpdatePlannedDate } from "../hooks";
import { plannedDateSchema, type PlannedDateFormValues } from "../schemas";
import type { PlannedDateChange, Project } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

function PlannedDateDialog({
  projectId,
  currentDate,
  open,
  onOpenChange,
}: {
  projectId: string;
  currentDate: string | null | undefined;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const mutation = useUpdatePlannedDate(projectId);
  const form = useForm<PlannedDateFormValues>({
    resolver: zodResolver(plannedDateSchema),
    defaultValues: { new_date: currentDate ?? "", reason: "" },
  });

  React.useEffect(() => {
    if (open) form.reset({ new_date: currentDate ?? "", reason: "" });
  }, [open, currentDate, form]);

  async function onSubmit(values: PlannedDateFormValues) {
    try {
      await mutation.mutateAsync({
        new_date: values.new_date || null,
        reason: values.reason,
      });
      toast.success("Planned completion date updated");
      onOpenChange(false);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Update planned completion date</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="new_date"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>New date</FormLabel>
                  <FormControl>
                    <Input type="date" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="reason"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Reason for change</FormLabel>
                  <FormControl>
                    <Textarea rows={3} placeholder="e.g. Scope extended by client, +2 weeks" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" loading={mutation.isPending}>
                Save
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

function PlannedDateChangeLog({ projectId }: { projectId: string }) {
  const [expanded, setExpanded] = React.useState(false);
  const query = usePlannedDateChanges(expanded ? projectId : undefined);
  const changes: PlannedDateChange[] = query.data ?? [];

  return (
    <div className="mt-2">
      <button
        type="button"
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded((e) => !e)}
      >
        {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        {expanded ? "Hide date history" : "Show date history"}
      </button>
      {expanded && (
        <div className="mt-2 space-y-2">
          {query.isLoading && <p className="text-xs text-muted-foreground">Loading…</p>}
          {!query.isLoading && changes.length === 0 && (
            <p className="text-xs text-muted-foreground">No changes recorded yet.</p>
          )}
          {changes.map((c) => (
            <div key={c.id} className="rounded-md border border-border bg-muted/30 px-3 py-2 text-xs">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {c.old_date ?? "—"} → {c.new_date ?? "—"}
                </span>
                <span className="text-muted-foreground">
                  {new Date(c.changed_at).toLocaleDateString()}
                </span>
              </div>
              <div className="mt-0.5 text-muted-foreground">
                {c.reason} · {c.changed_by_name}
              </div>
            </div>
          ))}
        </div>
      )}
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
  const [dateDialogOpen, setDateDialogOpen] = React.useState(false);
  // Active tab lives in the URL so leaving and returning keeps the same tab.
  const [activeTab, setActiveTab] = useUrlState("tab", "overview");

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
        className="mb-4"
        value={activeTab}
        onChange={setActiveTab}
        items={[
          { value: "overview", label: "Overview" },
          { value: "activities", label: "Activities" },
          { value: "submissions", label: "Submissions" },
        ]}
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
              <Row
                label="Planning Plant"
                value={
                  project.planning_plant_code ? (
                    <span className="font-mono">{project.planning_plant_code}</span>
                  ) : (
                    "—"
                  )
                }
              />
              <Row label="PP Description" value={project.planning_plant_description ?? "—"} />
              <Row
                label="Maintenance Plant"
                value={
                  project.maintenance_plant_code ? (
                    <span className="font-mono">{project.maintenance_plant_code}</span>
                  ) : (
                    "—"
                  )
                }
              />
              <Row label="MP Description" value={project.maintenance_plant_description ?? "—"} />
              <Row label="Project Name" value={project.client ?? "—"} />
              <Row label="Status" value={<StatusBadge status={project.status} />} />
              <Row label="Members" value={project.member_count} />
              <Row
                label="Days running"
                value={project.days_running != null ? `${project.days_running} days` : "—"}
              />
              <Row label="Start date" value={project.start_date ?? "—"} />
              <div className="py-2">
                <div className="flex items-center justify-between gap-4 text-sm">
                  <span className="text-muted-foreground">Planned completion</span>
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{project.planned_completion_date ?? "—"}</span>
                    {canManage && project.planned_completion_date && (
                      <button
                        type="button"
                        title="Update planned completion date"
                        onClick={() => setDateDialogOpen(true)}
                        className="text-muted-foreground hover:text-foreground"
                      >
                        <CalendarClock className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>
                <PlannedDateChangeLog projectId={project.id} />
              </div>
              <Row
                label="Actual completion"
                value={project.actual_completion_date ?? "—"}
              />
              {project.description && (
                <div className="py-2 text-sm">
                  <div className="mb-1 text-muted-foreground">Description</div>
                  <p className="whitespace-pre-wrap">{project.description}</p>
                </div>
              )}
            </CardContent>
          </Card>

          <ProjectMembers project={project} />

          <div className="md:col-span-2">
            <ProjectTimeline projectId={project.id} />
          </div>
        </div>
      )}

      {activeTab === "activities" && (
        <ActivitiesTab
          projectId={project.id}
          canManage={canManage}
          canEdit={canManage}
        />
      )}

      {activeTab === "submissions" && (
        <SubmissionsTab projectId={project.id} canManage={canManage} />
      )}

      <PlannedDateDialog
        projectId={project.id}
        currentDate={project.planned_completion_date}
        open={dateDialogOpen}
        onOpenChange={setDateDialogOpen}
      />

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
