"use client";

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Pencil, Trash2, X } from "lucide-react";
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
import { useProjectMembers } from "@/features/projects/hooks";
import { AppError } from "@/lib/api-client";
import { useAuth } from "@/features/auth/auth-provider";

import {
  useCreateDeliverable,
  useDeleteDeliverable,
  useDeliverables,
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

// ---------------------------------------------------------------------------
// Inline form (create / edit)
// ---------------------------------------------------------------------------

interface DeliverableFormPanelProps {
  projectId: string;
  editing: Deliverable | null;
  memberOptions: { id: string; name: string }[];
  onDone: () => void;
}

function DeliverableFormPanel({
  projectId,
  editing,
  memberOptions,
  onDone,
}: DeliverableFormPanelProps) {
  const createMutation = useCreateDeliverable(projectId);
  const updateMutation = useUpdateDeliverable(projectId, editing?.id ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const defaultValues: DeliverableFormValues = editing
    ? {
        name: editing.name,
        description: editing.description ?? "",
        target_date: editing.target_date ?? "",
        owner_employee_id: editing.owner_employee_id ?? "",
        status: editing.status,
        completion_date: editing.completion_date ?? "",
      }
    : EMPTY_DELIVERABLE_FORM;

  const form = useForm<DeliverableFormValues>({
    resolver: zodResolver(deliverableFormSchema),
    defaultValues,
  });

  async function onSubmit(values: DeliverableFormValues) {
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

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {editing ? "Edit Deliverable" : "Add Deliverable"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={(e) => { e.preventDefault(); void form.handleSubmit(onSubmit)(e); }} className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g. MDR Package" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="owner_employee_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Owner</FormLabel>
                    <Select value={field.value ?? ""} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select owner…" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="">— None —</SelectItem>
                        {memberOptions.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.name}
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
                    <FormLabel>Target Date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} value={field.value ?? ""} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="completion_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Completion Date</FormLabel>
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
// Deliverables tab
// ---------------------------------------------------------------------------

interface DeliverableTabProps {
  projectId: string;
  projectArchived?: boolean;
}

export function DeliverablesTab({ projectId, projectArchived }: DeliverableTabProps) {
  const { role, employeeId } = useAuth();

  const query = useDeliverables(projectId);
  const membersQuery = useProjectMembers(projectId);

  // PM always can manage; employees can manage if they are a team_lead on this project
  const isTeamLead = (membersQuery.data ?? []).some(
    (m) => m.employee_id === employeeId && m.role === "team_lead",
  );
  const canManage = role === "project_manager" || isTeamLead;
  const deleteMutation = useDeleteDeliverable(projectId);

  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<Deliverable | null>(null);
  const [pendingDelete, setPendingDelete] = React.useState<Deliverable | null>(null);

  const memberOptions = (membersQuery.data ?? []).map((m) => ({
    id: m.employee_id,
    name: m.employee_name,
  }));

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

  async function confirmDelete() {
    if (!pendingDelete) return;
    try {
      await deleteMutation.mutateAsync(pendingDelete.id);
      toast.success("Deliverable deleted");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not delete deliverable.");
    } finally {
      setPendingDelete(null);
    }
  }

  const deliverables = query.data ?? [];

  return (
    <div className="space-y-4">
      {/* Inline form */}
      {isFormOpen && !projectArchived && (
        <DeliverableFormPanel
          projectId={projectId}
          editing={editing}
          memberOptions={memberOptions}
          onDone={closeForm}
        />
      )}

      {/* Table card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <CardTitle>
            Deliverables
            {deliverables.length > 0 && (
              <span className="ml-2 text-sm font-normal text-muted-foreground">
                ({deliverables.length})
              </span>
            )}
          </CardTitle>
          {canManage && !projectArchived && !isFormOpen && (
            <Button size="sm" onClick={openAdd}>
              <Plus className="h-4 w-4 mr-1" />
              Add
            </Button>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {query.isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-2/3" />
              <Skeleton className="h-8 w-3/4" />
            </div>
          ) : deliverables.length === 0 ? (
            <p className="px-4 pb-4 text-sm text-muted-foreground">
              No deliverables yet.{" "}
              {canManage && !projectArchived && !isFormOpen && (
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
                  <TableHead>Name</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Target Date</TableHead>
                  <TableHead>Status</TableHead>
                  {canManage && !projectArchived && (
                    <TableHead className="w-20 text-right">Actions</TableHead>
                  )}
                </TableRow>
              </TableHeader>
              <TableBody>
                {deliverables.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">
                      <div>{d.name}</div>
                      {d.description && (
                        <div className="text-xs text-muted-foreground mt-0.5 line-clamp-1">
                          {d.description}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      {d.owner_name ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell className="text-sm">
                      {d.target_date ?? <span className="text-muted-foreground">—</span>}
                    </TableCell>
                    <TableCell>
                      <DeliverableStatusBadge status={d.status} />
                    </TableCell>
                    {canManage && !projectArchived && (
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Edit"
                            onClick={() => openEdit(d)}
                          >
                            <Pencil className="h-4 w-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            aria-label="Delete"
                            onClick={() => setPendingDelete(d)}
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

      {/* Delete confirmation */}
      <AlertDialog
        open={pendingDelete !== null}
        onOpenChange={(open) => { if (!open) setPendingDelete(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete deliverable?</AlertDialogTitle>
            <AlertDialogDescription>
              &quot;{pendingDelete?.name}&quot; will be permanently deleted.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => { e.preventDefault(); void confirmDelete(); }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
