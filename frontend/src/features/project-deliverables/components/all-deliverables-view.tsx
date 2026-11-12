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
import { useUrlState } from "@/lib/use-url-state";

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
import { canManageRow, creatableProjects } from "../manage-access";
import {
  ALL,
  filterDeliverables,
  isFiltered,
  projectFilterOptions,
} from "../list-filters";
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

  async function onSubmit(values: DeliverableFormValues) {
    if (!editing && !projectId) {
      toast.error("Select a project first.");
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
                      <FormLabel>Reason for change (optional)</FormLabel>
                      <FormControl>
                        <Textarea
                          placeholder="Optional - why the planned submission date or status changed"
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
  const { role, employeeId } = useAuth();

  const query = useAllDeliverables();
  const projectsQuery = useProjects({ q: "", status: "active", limit: 100, offset: 0 });

  // PM: every project. Project Head: only the projects they head. The backend
  // enforces the same rule on every write; this only decides what to show.
  const projectOptions: ProjectOption[] = creatableProjects(
    role,
    employeeId,
    projectsQuery.data?.items ?? [],
  ).map((p) => ({
    id: p.id,
    label: p.code ? `${p.code} — ${p.name}` : p.name,
  }));
  const canAdd = projectOptions.length > 0;

  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<Deliverable | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<Deliverable | null>(null);

  const isFormOpen = showForm || editing !== null;

  // Filters live in the URL so they survive opening a deliverable and coming back.
  const [projectFilter, setProjectFilter] = useUrlState("project", ALL);
  const [activityFilter, setActivityFilter] = useUrlState("activity", "");
  const [statusFilter, setStatusFilter] = useUrlState("status", ALL);
  const filters = { project: projectFilter, activity: activityFilter, status: statusFilter };

  function clearFilters() {
    setProjectFilter(ALL);
    setActivityFilter("");
    setStatusFilter(ALL);
  }

  // While adding/editing, the page shows ONLY the form (no list) - start at the top.
  function openAdd() {
    setEditing(null);
    setShowForm(true);
    window.scrollTo({ top: 0 });
  }
  function openEdit(d: Deliverable) {
    setShowForm(false);
    setEditing(d);
    window.scrollTo({ top: 0 });
  }
  function closeForm() {
    setShowForm(false);
    setEditing(null);
  }

  const deliverables = query.data ?? [];
  const visible = filterDeliverables(deliverables, filters);
  const projectFilterItems = projectFilterOptions(deliverables);
  const filtered = isFiltered(filters);
  // Edit/Delete follow the backend's per-row `can_manage` for this caller.
  const showActions = visible.some(canManageRow);

  return (
    <>
      <Link href="/projects" className="text-sm text-primary hover:underline">
        ← Back
      </Link>
      <PageHeader
        className="mt-2"
        title="Deliverables"
        actions={
          canAdd && !isFormOpen ? (
            <Button onClick={openAdd}>
              <Plus className="h-4 w-4" />
              Add Deliverable
            </Button>
          ) : null
        }
      />

      {isFormOpen ? (
        <DeliverableFormPanel
          editing={editing}
          projectOptions={projectOptions}
          onDone={closeForm}
        />
      ) : (
      <>
      {deliverables.length > 0 && (
        <div className="mb-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_minmax(0,0.8fr)_auto] sm:items-end">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Project</label>
            <Select value={projectFilter} onValueChange={setProjectFilter}>
              <SelectTrigger aria-label="Filter by project">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All projects</SelectItem>
                {projectFilterItems.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Activity</label>
            <Input
              aria-label="Filter by activity"
              placeholder="Search activity…"
              value={activityFilter}
              onChange={(e) => setActivityFilter(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Status</label>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger aria-label="Filter by status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>All statuses</SelectItem>
                {DELIVERABLE_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {DELIVERABLE_STATUS_LABEL[s]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Button variant="ghost" disabled={!filtered} onClick={clearFilters}>
            Clear
          </Button>
        </div>
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
              {canAdd && !isFormOpen && (
                <button
                  type="button"
                  className="text-primary underline-offset-2 hover:underline"
                  onClick={openAdd}
                >
                  Add the first one.
                </button>
              )}
            </p>
          ) : !visible.length ? (
            <p className="p-4 text-sm text-muted-foreground">
              No deliverables match these filters.{" "}
              <button
                type="button"
                className="text-primary underline-offset-2 hover:underline"
                onClick={clearFilters}
              >
                Clear filters
              </button>
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Project</TableHead>
                  <TableHead>Activity</TableHead>
                  <TableHead>Planned Submission</TableHead>
                  <TableHead>Status</TableHead>
                  {showActions && <TableHead className="w-20 text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {visible.map((d) => (
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
                    {showActions && (
                      <TableCell className="text-right">
                        {canManageRow(d) && (
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
                        )}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      </>
      )}

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
