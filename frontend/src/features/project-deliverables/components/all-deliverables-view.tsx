"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { useAuth } from "@/features/auth/auth-provider";
import { useProjects } from "@/features/projects/hooks";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import {
  useAllDeliverables,
  useCreateDeliverable,
  useDeleteDeliverable,
  useUpdateDeliverable,
} from "../hooks";
import {
  DELIVERABLE_STATUSES,
  deliverableFormSchema,
  EMPTY_DELIVERABLE_FORM,
  toCreateBody,
  toUpdateBody,
  type DeliverableFormValues,
} from "../schemas";
import { DELIVERABLE_STATUS_LABEL, type Deliverable } from "../types";
import { DeliverableStatusBadge } from "./status-badge";

interface ProjectOption {
  id: string;
  label: string;
}

// ---------------------------------------------------------------------------
// Create / edit form (project selectable on create, locked on edit)
// ---------------------------------------------------------------------------

function DeliverableFormPanel({
  editing,
  projectOptions,
  onDone,
}: {
  editing: Deliverable | null;
  projectOptions: ProjectOption[];
  onDone: () => void;
}) {
  const [projectId, setProjectId] = React.useState(editing?.project_id ?? "");

  const createMutation = useCreateDeliverable(projectId);
  const updateMutation = useUpdateDeliverable(
    editing?.project_id ?? projectId,
    editing?.id ?? "",
  );
  const isPending = createMutation.isPending || updateMutation.isPending;

  const form = useForm<DeliverableFormValues>({
    resolver: zodResolver(deliverableFormSchema),
    defaultValues: editing
      ? {
          name: editing.name,
          description: editing.description ?? "",
          planned_start_date: editing.planned_start_date ?? "",
          target_date: editing.target_date ?? "",
          owner_employee_id: editing.owner_employee_id ?? "",
          status: editing.status,
          completion_date: editing.completion_date ?? "",
          reason: "",
        }
      : EMPTY_DELIVERABLE_FORM,
  });

  // Which tracked fields changed vs the original — used to require a reason.
  function trackedChanged(v: DeliverableFormValues): boolean {
    if (!editing) return false;
    const submissionChanged = (v.target_date || "") !== (editing.target_date ?? "");
    const reversal = editing.status === "completed" && v.status !== "completed";
    return submissionChanged || reversal;
  }

  async function onSubmit(values: DeliverableFormValues) {
    if (!editing && !projectId) {
      toast.error("Select a project first.");
      return;
    }
    if (trackedChanged(values) && !values.reason?.trim()) {
      form.setError("reason", {
        message:
          "A reason is required when changing the planned submission date or reverting status.",
      });
      return;
    }
    try {
      if (editing) {
        await updateMutation.mutateAsync(toUpdateBody(values));
        toast.success("Deliverable updated");
      } else {
        await createMutation.mutateAsync(toCreateBody(values));
        toast.success("Deliverable created");
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Failed to save deliverable.");
    }
  }

  const showReason = editing !== null;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {editing ? "Edit Deliverable" : "Add Deliverable"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void form.handleSubmit(onSubmit)(e);
            }}
            className="space-y-4"
          >
            <div className="grid gap-4 sm:grid-cols-2">
              {!editing && (
                <div className="sm:col-span-2 space-y-2">
                  <label className="text-sm font-medium leading-none">Project *</label>
                  <Select value={projectId} onValueChange={setProjectId}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select project…" />
                    </SelectTrigger>
                    <SelectContent>
                      {projectOptions.map((p) => (
                        <SelectItem key={p.id} value={p.id}>
                          {p.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Activity Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. MDR Package" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Status</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {DELIVERABLE_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {DELIVERABLE_STATUS_LABEL[s]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="target_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Planned Submission</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Description</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Optional details…"
                        className="resize-none"
                        rows={2}
                        {...field}
                        value={field.value ?? ""}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {showReason && (
                <FormField
                  control={form.control}
                  name="reason"
                  render={({ field }) => (
                    <FormItem className="sm:col-span-2">
                      <FormLabel>Reason for change</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Required when changing the planned submission date or reverting status"
                          className="resize-none"
                          rows={2}
                          {...field}
                          value={field.value ?? ""}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

            <div className="flex gap-2">
              <Button type="submit" loading={isPending}>
                {editing ? "Save Changes" : "Add Deliverable"}
              </Button>
              <Button type="button" variant="secondary" onClick={onDone}>
                <X className="h-4 w-4 mr-1" />
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Delete confirmation (project-scoped mutation)
// ---------------------------------------------------------------------------

function DeleteDeliverableDialog({
  target,
  onOpenChange,
  onDeleted,
}: {
  target: Deliverable | null;
  onOpenChange: (open: boolean) => void;
  onDeleted: () => void;
}) {
  const deleteMutation = useDeleteDeliverable(target?.project_id ?? "");

  async function confirm() {
    if (!target) return;
    try {
      await deleteMutation.mutateAsync(target.id);
      toast.success("Deliverable deleted");
      onDeleted();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not delete deliverable.");
    }
  }

  return (
    <AlertDialog open={target !== null} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete deliverable?</AlertDialogTitle>
          <AlertDialogDescription>
            &quot;{target?.name}&quot; will be permanently deleted.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              e.preventDefault();
              void confirm();
            }}
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// View
// ---------------------------------------------------------------------------

export function AllDeliverablesView() {
  const router = useRouter();
  const { role } = useAuth();
  const canManage = can(role, "project.manage");

  const query = useAllDeliverables();
  const projectsQuery = useProjects({ q: "", status: "active", limit: 100, offset: 0 });

  const projectOptions: ProjectOption[] = (projectsQuery.data?.items ?? []).map((p) => ({
    id: p.id,
    label: p.code ? `${p.code} — ${p.name}` : p.name,
  }));

  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<Deliverable | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<Deliverable | null>(null);

  const isFormOpen = showForm || editing !== null;

  function openAdd() {
    setEditing(null);
    setShowForm(true);
  }
  function openEdit(d: Deliverable) {
    setShowForm(false);
    setEditing(d);
  }
  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  const deliverables = query.data ?? [];

  return (
    <>
      <Link href="/projects" className="text-sm text-primary hover:underline">
        ← Back
      </Link>
      <PageHeader
        className="mt-2"
        title="Deliverables"
        actions={
          canManage && !isFormOpen ? (
            <Button onClick={openAdd}>
              <Plus className="h-4 w-4" />
              Add Deliverable
            </Button>
          ) : null
        }
      />

      {isFormOpen && (
        <DeliverableFormPanel
          editing={editing}
          projectOptions={projectOptions}
          onDone={closeForm}
        />
      )}

      <Card>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-5/6" />
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : query.isError ? (
            <ErrorState
              title="Could not load deliverables"
              message="Please try again."
              onRetry={() => void query.refetch()}
            />
          ) : !deliverables.length ? (
            <p className="p-4 text-sm text-muted-foreground">
              No deliverables found.{" "}
              {canManage && !isFormOpen && (
                <button
                  type="button"
                  className="text-primary underline-offset-2 hover:underline"
                  onClick={openAdd}
                >
                  Add the first one.
                </button>
              )}
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Activity</TableHead>
                  <TableHead>Planned Submission</TableHead>
                  <TableHead>Status</TableHead>
                  {canManage && <TableHead className="w-20 text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {deliverables.map((d) => (
                  <TableRow
                    key={d.id}
                    className="cursor-pointer"
                    onClick={() => router.push(`/projects/deliverables/${d.id}`)}
                  >
                    <TableCell className="text-sm">
                      <Link
                        href={`/projects/${d.project_id}`}
                        className="text-primary hover:underline font-mono"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {d.project_code ?? d.project_id}
                      </Link>
                    </TableCell>
                    <TableCell className="font-medium">{d.name}</TableCell>
                    <TableCell className="text-sm">
                      {d.target_date ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <DeliverableStatusBadge status={d.status} />
                    </TableCell>
                    {canManage && (
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Edit"
                            onClick={(e) => {
                              e.stopPropagation();
                              openEdit(d);
                            }}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Delete"
                            onClick={(e) => {
                              e.stopPropagation();
                              setPendingDelete(d);
                            }}
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <DeleteDeliverableDialog
        target={pendingDelete}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null);
        }}
        onDeleted={() => setPendingDelete(null)}
      />
    </>
  );
}
