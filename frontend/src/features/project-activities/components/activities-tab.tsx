"use client";

import * as React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Pencil, Plus, Trash2, ChevronDown, ChevronUp } from "lucide-react";
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
import { Badge } from "@/components/ui/badge";
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
import { Textarea } from "@/components/ui/textarea";
import { useActivityTypeOptions } from "@/features/activity-types/hooks";
import { AppError } from "@/lib/api-client";

import {
  useCreateActivity,
  useDeleteActivity,
  useProjectActivities,
  useUpdateActivity,
} from "../hooks";
import { activityFormSchema, type ActivityFormValues } from "../schemas";
import type { ActivityStatus, ProjectActivity } from "../types";
import { ACTIVITY_STATUS_LABEL } from "../types";

// ── status badge ─────────────────────────────────────────────────────────────

const STATUS_VARIANT: Record<ActivityStatus, "neutral" | "info" | "success"> = {
  open: "neutral",
  in_progress: "info",
  closed: "success",
};

function StatusBadge({ status }: { status: ActivityStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]} dot>
      {ACTIVITY_STATUS_LABEL[status]}
    </Badge>
  );
}

// ── inline status changer (team lead + PM) ───────────────────────────────────

const STATUSES: ActivityStatus[] = ["open", "in_progress", "closed"];

function StatusSelect({
  projectId,
  activity,
}: {
  projectId: string;
  activity: ProjectActivity;
}) {
  const mutation = useUpdateActivity(projectId, activity.id);

  return (
    <Select
      value={activity.status}
      onValueChange={async (val) => {
        try {
          await mutation.mutateAsync({ status: val as ActivityStatus });
        } catch {
          toast.error("Could not update status");
        }
      }}
      disabled={mutation.isPending}
    >
      <SelectTrigger className="h-7 w-36 text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {STATUSES.map((s) => (
          <SelectItem key={s} value={s} className="text-xs">
            {ACTIVITY_STATUS_LABEL[s]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

// ── activity form (create / edit) ─────────────────────────────────────────────

interface ActivityFormProps {
  projectId: string;
  existing?: ProjectActivity;
  onDone: () => void;
  onCancel: () => void;
}

function ActivityForm({ projectId, existing, onDone, onCancel }: ActivityFormProps) {
  const isEdit = !!existing;
  const { items: activityTypes } = useActivityTypeOptions();

  const form = useForm<ActivityFormValues>({
    resolver: zodResolver(activityFormSchema),
    defaultValues: existing
      ? {
          activity_type_id: existing.activity_type_id ?? undefined,
          title: existing.title,
          status: existing.status as ActivityStatus,
          assigned_to_id: existing.assigned_to_id ?? undefined,
          target_date: existing.target_date ?? "",
          remarks: existing.remarks ?? "",
          sort_order: existing.sort_order,
        }
      : {
          activity_type_id: undefined,
          title: "",
          status: "open",
          assigned_to_id: undefined,
          target_date: "",
          remarks: "",
          sort_order: 0,
        },
  });

  const createMut = useCreateActivity(projectId);
  const updateMut = useUpdateActivity(projectId, existing?.id ?? "");
  const isPending = createMut.isPending || updateMut.isPending;

  async function onSubmit(values: ActivityFormValues) {
    const body = {
      activity_type_id: values.activity_type_id ?? null,
      title: values.title,
      status: values.status,
      assigned_to_id: values.assigned_to_id ?? null,
      target_date: values.target_date || null,
      remarks: values.remarks || null,
      sort_order: values.sort_order,
    };
    try {
      if (isEdit) {
        await updateMut.mutateAsync(body);
        toast.success("Activity updated");
      } else {
        await createMut.mutateAsync(body);
        toast.success("Activity added");
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong");
    }
  }

  return (
    <Form {...form}>
      <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
        <div className="grid gap-4 sm:grid-cols-2">
          {/* Category */}
          <FormField
            control={form.control}
            name="activity_type_id"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Category{" "}
                  <span className="font-normal text-muted-foreground">(optional)</span>
                </FormLabel>
                <Select
                  value={field.value ?? ""}
                  onValueChange={(v) => field.onChange(v === "__none__" ? null : v)}
                >
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder="Select category…" />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    <SelectItem value="__none__">— None —</SelectItem>
                    {activityTypes.map((at) => (
                      <SelectItem key={at.id} value={at.id}>
                        {at.code ? `${at.code} — ${at.name}` : at.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Status */}
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
                    {STATUSES.map((s) => (
                      <SelectItem key={s} value={s}>
                        {ACTIVITY_STATUS_LABEL[s]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Title — full width */}
          <FormField
            control={form.control}
            name="title"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>Activity description</FormLabel>
                <FormControl>
                  <Input placeholder="e.g. Updating FMTL data changes in MTL data" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Target date */}
          <FormField
            control={form.control}
            name="target_date"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Target date{" "}
                  <span className="font-normal text-muted-foreground">(optional)</span>
                </FormLabel>
                <FormControl>
                  <Input type="date" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Sort order */}
          <FormField
            control={form.control}
            name="sort_order"
            render={({ field }) => (
              <FormItem>
                <FormLabel>
                  Order{" "}
                  <span className="font-normal text-muted-foreground">(lower = first)</span>
                </FormLabel>
                <FormControl>
                  <Input type="number" min={0} {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />

          {/* Remarks — full width */}
          <FormField
            control={form.control}
            name="remarks"
            render={({ field }) => (
              <FormItem className="sm:col-span-2">
                <FormLabel>
                  Remarks{" "}
                  <span className="font-normal text-muted-foreground">(optional)</span>
                </FormLabel>
                <FormControl>
                  <Textarea rows={2} placeholder="Blockers, notes, references…" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button type="submit" loading={isPending}>
            {isEdit ? "Save changes" : "Add activity"}
          </Button>
        </div>
      </form>
    </Form>
  );
}

// ── activity row ──────────────────────────────────────────────────────────────

function ActivityRow({
  projectId,
  activity,
  canManage,
  canEdit,
  onEdit,
  onDelete,
}: {
  projectId: string;
  activity: ProjectActivity;
  canManage: boolean;
  canEdit: boolean;   // PM = true, team_lead = false (status only)
  onEdit: (a: ProjectActivity) => void;
  onDelete: (a: ProjectActivity) => void;
}) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="border-b border-border last:border-0">
      <div className="flex items-start gap-3 py-3 px-1">
        {/* Expand toggle for remarks */}
        <button
          type="button"
          className="mt-0.5 text-muted-foreground hover:text-foreground"
          onClick={() => setExpanded((e) => !e)}
          aria-label={expanded ? "Collapse" : "Expand"}
        >
          {expanded
            ? <ChevronUp className="h-4 w-4" />
            : <ChevronDown className="h-4 w-4" />}
        </button>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {activity.activity_type_name && (
              <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-medium text-muted-foreground">
                {activity.activity_type_name}
              </span>
            )}
            <span className="text-sm font-medium">{activity.title}</span>
          </div>

          <div className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {activity.assigned_to_name && (
              <span>Assigned: <span className="text-foreground">{activity.assigned_to_name}</span></span>
            )}
            {activity.target_date && (
              <span>Target: <span className="text-foreground">{activity.target_date}</span></span>
            )}
            {activity.closed_date && (
              <span>Closed: <span className="text-foreground">{activity.closed_date}</span></span>
            )}
          </div>

          {expanded && activity.remarks && (
            <p className="mt-2 text-xs text-muted-foreground whitespace-pre-wrap">
              {activity.remarks}
            </p>
          )}
        </div>

        {/* Status + actions */}
        <div className="flex shrink-0 items-center gap-2">
          {canManage ? (
            <StatusSelect projectId={projectId} activity={activity} />
          ) : (
            <StatusBadge status={activity.status as ActivityStatus} />
          )}
          {canEdit && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onEdit(activity)}
                aria-label="Edit"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onDelete(activity)}
                aria-label="Delete"
              >
                <Trash2 className="h-3.5 w-3.5 text-destructive" />
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── main tab ──────────────────────────────────────────────────────────────────

export function ActivitiesTab({
  projectId,
  canManage,  // PM
  canEdit,    // PM
}: {
  projectId: string;
  canManage: boolean;
  canEdit: boolean;
}) {
  const query = useProjectActivities(projectId);
  const deleteMut = useDeleteActivity(projectId);

  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<ProjectActivity | null>(null);
  const [deleting, setDeleting] = React.useState<ProjectActivity | null>(null);

  const activities = query.data ?? [];

  // Group by activity type
  const groups = React.useMemo(() => {
    const map = new Map<string, { label: string; items: ProjectActivity[] }>();
    for (const a of activities) {
      const key = a.activity_type_id ?? "__none__";
      const label = a.activity_type_name ?? "Uncategorised";
      if (!map.has(key)) map.set(key, { label, items: [] });
      map.get(key)!.items.push(a);
    }
    return Array.from(map.values());
  }, [activities]);

  const stats = React.useMemo(() => ({
    total: activities.length,
    open: activities.filter((a) => a.status === "open").length,
    in_progress: activities.filter((a) => a.status === "in_progress").length,
    closed: activities.filter((a) => a.status === "closed").length,
  }), [activities]);

  if (editing) {
    return (
      <Card>
        <CardHeader><CardTitle>Edit Activity</CardTitle></CardHeader>
        <CardContent>
          <ActivityForm
            projectId={projectId}
            existing={editing}
            onDone={() => setEditing(null)}
            onCancel={() => setEditing(null)}
          />
        </CardContent>
      </Card>
    );
  }

  if (showForm) {
    return (
      <Card>
        <CardHeader><CardTitle>Add Activity</CardTitle></CardHeader>
        <CardContent>
          <ActivityForm
            projectId={projectId}
            onDone={() => setShowForm(false)}
            onCancel={() => setShowForm(false)}
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      {activities.length > 0 && (
        <div className="flex flex-wrap gap-3">
          <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
            <div className="text-2xl font-semibold tabular">{stats.total}</div>
            <div className="text-xs text-muted-foreground">Total</div>
          </div>
          <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
            <div className="text-2xl font-semibold tabular">{stats.open}</div>
            <div className="text-xs text-muted-foreground">Open</div>
          </div>
          <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
            <div className="text-2xl font-semibold tabular text-primary">{stats.in_progress}</div>
            <div className="text-xs text-muted-foreground">In Progress</div>
          </div>
          <div className="rounded-md border border-border bg-card px-4 py-2 text-center">
            <div className="text-2xl font-semibold tabular text-success">{stats.closed}</div>
            <div className="text-xs text-muted-foreground">Closed</div>
          </div>
        </div>
      )}

      {/* Add button */}
      {canEdit && (
        <div className="flex justify-end">
          <Button onClick={() => setShowForm(true)}>
            <Plus className="h-4 w-4" />
            Add activity
          </Button>
        </div>
      )}

      {/* Loading */}
      {query.isLoading && (
        <Card>
          <CardContent className="pt-4 space-y-3">
            {[1, 2, 3].map((n) => <Skeleton key={n} className="h-12 w-full" />)}
          </CardContent>
        </Card>
      )}

      {/* Empty */}
      {!query.isLoading && activities.length === 0 && (
        <Card>
          <CardContent className="py-12 text-center text-sm text-muted-foreground">
            No activities yet.{canEdit ? " Add the first one above." : ""}
          </CardContent>
        </Card>
      )}

      {/* Grouped list */}
      {!query.isLoading && groups.map((group) => (
        <Card key={group.label}>
          <CardHeader className="pb-0 pt-4">
            <CardTitle className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
              {group.label}
              <span className="ml-2 font-normal normal-case tracking-normal">
                ({group.items.filter((a) => a.status === "closed").length}/{group.items.length} closed)
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-2">
            {group.items.map((activity) => (
              <ActivityRow
                key={activity.id}
                projectId={projectId}
                activity={activity}
                canManage={canManage}
                canEdit={canEdit}
                onEdit={setEditing}
                onDelete={setDeleting}
              />
            ))}
          </CardContent>
        </Card>
      ))}

      {/* Delete confirm */}
      <AlertDialog open={!!deleting} onOpenChange={(o) => { if (!o) setDeleting(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete activity?</AlertDialogTitle>
            <AlertDialogDescription>
              &ldquo;{deleting?.title}&rdquo; will be permanently removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (!deleting) return;
                try {
                  await deleteMut.mutateAsync(deleting.id);
                  toast.success("Activity deleted");
                  setDeleting(null);
                } catch {
                  toast.error("Could not delete activity");
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
