"use client";

import * as React from "react";
import { ChevronDown, ChevronRight, PencilLine, PlusCircle, Power, PowerOff } from "lucide-react";
import { toast } from "sonner";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";
import { formatInt } from "@/lib/format";

import {
  useActivities,
  useCreateActivity,
  useCreateSubActivity,
  useDeactivateActivity,
  useDeactivateSubActivity,
  useReactivateActivity,
  useReactivateSubActivity,
  useSubActivities,
  useUpdateActivity,
  useUpdateSubActivity,
} from "../hooks";
import type { ActivityMaster, BenchmarkType, RelevantCountField } from "../types";

const NONE = "__none__";
const BENCHMARK_TYPES = ["NUMERIC", "TASK_BASED"] as const;
const BENCHMARK_TYPE_LABEL: Record<BenchmarkType, string> = {
  NUMERIC: "Numeric (count vs. target)",
  TASK_BASED: "Task-based (duration + status only)",
};
const COUNT_FIELDS = ["tags", "docs", "bom", "spares"] as const;
const COUNT_FIELD_LABEL: Record<RelevantCountField, string> = {
  tags: "Tag Count",
  docs: "Document Count",
  bom: "BOM Count",
  spares: "Spares Count",
};

// ── Activity form ────────────────────────────────────────────────────────────

const activityFormSchema = z.object({
  code: z.string().trim().max(50).optional().default(""),
  name: z.string().trim().min(1, "Name is required").max(200),
});
type ActivityFormValues = z.infer<typeof activityFormSchema>;

function ActivityForm({
  editing,
  onDone,
}: {
  editing: ActivityMaster | null;
  onDone: () => void;
}) {
  const createMutation = useCreateActivity();
  const updateMutation = useUpdateActivity(editing?.id ?? "");

  const form = useForm<ActivityFormValues>({
    resolver: zodResolver(activityFormSchema),
    defaultValues: editing
      ? { code: editing.code ?? "", name: editing.name }
      : { code: "", name: "" },
  });

  async function onSubmit(values: ActivityFormValues) {
    try {
      if (editing) {
        await updateMutation.mutateAsync({ name: values.name });
        toast.success("Activity updated");
      } else {
        await createMutation.mutateAsync({ code: values.code || null, name: values.name });
        toast.success("Activity created");
        form.reset({ code: "", name: "" });
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong.");
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">{editing ? `Edit: ${editing.name}` : "New Activity"}</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3" noValidate>
            <div className="grid gap-3 sm:grid-cols-4">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code (optional)</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. FMTL" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-3">
                    <FormLabel>Activity Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. FMTL" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="flex gap-2">
              <Button type="submit" loading={isPending} size="sm">
                {editing ? "Save changes" : "Create"}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onDone}>
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

// ── Sub-Activity form ────────────────────────────────────────────────────────

const subActivityFormSchema = z
  .object({
    code: z.string().trim().max(50).optional().default(""),
    name: z.string().trim().min(1, "Name is required").max(200),
    benchmark_type: z.union([z.enum(BENCHMARK_TYPES), z.literal(NONE)]),
    benchmark_value: z.string().optional().default(""),
    benchmark_period_days: z.string().optional().default(""),
    benchmark_unit_note: z.string().trim().max(100).optional().default(""),
    benchmark_remarks: z.string().trim().max(500).optional().default(""),
    relevant_count_field: z.union([z.enum(COUNT_FIELDS), z.literal(NONE)]),
  })
  .superRefine((v, ctx) => {
    if (v.benchmark_type === "NUMERIC" && !v.benchmark_value.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Required for a Numeric benchmark",
        path: ["benchmark_value"],
      });
    }
    if (v.benchmark_type === "NUMERIC" && v.relevant_count_field === NONE) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "Required — this is the field the benchmark reads as the actual value",
        path: ["relevant_count_field"],
      });
    }
  });
type SubActivityFormValues = z.infer<typeof subActivityFormSchema>;

const EMPTY_SUB: SubActivityFormValues = {
  code: "",
  name: "",
  benchmark_type: NONE,
  benchmark_value: "",
  benchmark_period_days: "",
  benchmark_unit_note: "",
  benchmark_remarks: "",
  relevant_count_field: NONE,
};

function SubActivityForm({
  activityId,
  editing,
  onDone,
}: {
  activityId: string;
  editing: ActivityMaster | null;
  onDone: () => void;
}) {
  const createMutation = useCreateSubActivity(activityId);
  const updateMutation = useUpdateSubActivity(editing?.id ?? "");

  const form = useForm<SubActivityFormValues>({
    resolver: zodResolver(subActivityFormSchema),
    defaultValues: editing
      ? {
          code: editing.code ?? "",
          name: editing.name,
          benchmark_type: editing.benchmark_type ?? NONE,
          benchmark_value: editing.benchmark_value != null ? String(editing.benchmark_value) : "",
          benchmark_period_days:
            editing.benchmark_period_days != null ? String(editing.benchmark_period_days) : "",
          benchmark_unit_note: editing.benchmark_unit_note ?? "",
          benchmark_remarks: editing.benchmark_remarks ?? "",
          relevant_count_field: editing.relevant_count_field ?? NONE,
        }
      : EMPTY_SUB,
  });

  const benchmarkType = form.watch("benchmark_type");

  async function onSubmit(values: SubActivityFormValues) {
    const body = {
      code: values.code || null,
      name: values.name,
      benchmark_type: values.benchmark_type === NONE ? null : values.benchmark_type,
      benchmark_value:
        values.benchmark_type === "NUMERIC" && values.benchmark_value.trim()
          ? Number(values.benchmark_value)
          : null,
      benchmark_period_days: values.benchmark_period_days.trim()
        ? Number(values.benchmark_period_days)
        : null,
      benchmark_unit_note: values.benchmark_unit_note || null,
      benchmark_remarks: values.benchmark_remarks || null,
      relevant_count_field: values.relevant_count_field === NONE ? null : values.relevant_count_field,
    };
    try {
      if (editing) {
        await updateMutation.mutateAsync(body);
        toast.success("Sub-activity updated");
      } else {
        await createMutation.mutateAsync(body);
        toast.success("Sub-activity created");
        form.reset(EMPTY_SUB);
      }
      onDone();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Something went wrong.");
    }
  }

  const isPending = createMutation.isPending || updateMutation.isPending;

  return (
    <Card className="mb-4">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          {editing ? `Edit: ${editing.name}` : "New Sub-Activity"}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3" noValidate>
            <div className="grid gap-3 sm:grid-cols-3">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code (optional)</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Sub-Activity Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. FMTL-REWORK" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              <FormField
                control={form.control}
                name="benchmark_type"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Benchmark Type</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>No benchmark (pure logging)</SelectItem>
                        {BENCHMARK_TYPES.map((t) => (
                          <SelectItem key={t} value={t}>
                            {BENCHMARK_TYPE_LABEL[t]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {benchmarkType === "NUMERIC" && (
                <FormField
                  control={form.control}
                  name="benchmark_value"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Benchmark Value</FormLabel>
                      <FormControl>
                        <Input {...field} inputMode="decimal" placeholder="e.g. 250" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
              {benchmarkType !== NONE && (
                <FormField
                  control={form.control}
                  name="benchmark_period_days"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Period (days)</FormLabel>
                      <FormControl>
                        <Input {...field} inputMode="numeric" placeholder="e.g. 1" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>
            {benchmarkType !== NONE && (
              <div className="grid gap-3 sm:grid-cols-2">
                {benchmarkType === "NUMERIC" && (
                  <FormField
                    control={form.control}
                    name="relevant_count_field"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Benchmark Source Field <span className="text-destructive">*</span>
                        </FormLabel>
                        <Select
                          value={field.value === NONE ? undefined : field.value}
                          onValueChange={field.onChange}
                        >
                          <FormControl>
                            <SelectTrigger>
                              <SelectValue placeholder="Select field…" />
                            </SelectTrigger>
                          </FormControl>
                          <SelectContent>
                            {COUNT_FIELDS.map((c) => (
                              <SelectItem key={c} value={c}>
                                {COUNT_FIELD_LABEL[c]}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <p className="text-xs text-muted-foreground">
                          The benchmark compares against this existing count field — there is
                          no separate "actual" entry.
                        </p>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                )}
                <FormField
                  control={form.control}
                  name="benchmark_unit_note"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Unit note (optional)</FormLabel>
                      <FormControl>
                        <Input {...field} placeholder="e.g. PAGES" />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>
            )}
            <FormField
              control={form.control}
              name="benchmark_remarks"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Remarks (optional)</FormLabel>
                  <FormControl>
                    <Textarea {...field} rows={2} placeholder="Source notes, e.g. '500 REQUIRED PAGES/DAY'" />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <div className="flex gap-2">
              <Button type="submit" loading={isPending} size="sm">
                {editing ? "Save changes" : "Create"}
              </Button>
              <Button type="button" variant="ghost" size="sm" onClick={onDone}>
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}

// ── Sub-Activities panel (shown when an Activity is expanded) ───────────────

function SubActivitiesPanel({ activity }: { activity: ActivityMaster }) {
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<ActivityMaster | null>(null);

  const query = useSubActivities(activity.id, false);
  const deactivateMutation = useDeactivateSubActivity();
  const reactivateMutation = useReactivateSubActivity();

  const items = query.data ?? [];

  function closeForm() {
    setEditing(null);
    setShowForm(false);
  }

  async function handleDeactivate(sub: ActivityMaster) {
    try {
      await deactivateMutation.mutateAsync(sub.id);
      toast.success(`"${sub.name}" deactivated`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not deactivate.");
    }
  }

  async function handleReactivate(sub: ActivityMaster) {
    try {
      await reactivateMutation.mutateAsync(sub.id);
      toast.success(`"${sub.name}" reactivated`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not reactivate.");
    }
  }

  return (
    <div className="space-y-3 border-t border-border bg-muted/30 p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium text-muted-foreground">
          Sub-Activities of &ldquo;{activity.name}&rdquo;
        </h4>
        {!showForm && (
          <Button size="sm" variant="secondary" onClick={() => { setEditing(null); setShowForm(true); }}>
            <PlusCircle className="h-4 w-4" />
            New Sub-Activity
          </Button>
        )}
      </div>

      {showForm && (
        <SubActivityForm activityId={activity.id} editing={editing} onDone={closeForm} />
      )}

      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Sub-Activity</TableHead>
              <TableHead className="w-44">Benchmark</TableHead>
              <TableHead className="w-24 text-center">Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!query.isLoading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No sub-activities yet.
                </TableCell>
              </TableRow>
            )}
            {items.map((sub) => (
              <TableRow key={sub.id} className={!sub.is_active ? "opacity-50" : ""}>
                <TableCell className="font-medium">{sub.name}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {sub.benchmark_type === "NUMERIC" &&
                    `${formatInt(sub.benchmark_value)} / ${sub.benchmark_period_days ?? 1}d` +
                    (sub.relevant_count_field ? ` (${COUNT_FIELD_LABEL[sub.relevant_count_field]})` : "")}
                  {sub.benchmark_type === "TASK_BASED" && "Task-based"}
                  {!sub.benchmark_type && "—"}
                </TableCell>
                <TableCell className="text-center">
                  <Badge variant={sub.is_active ? "success" : "neutral"} dot>
                    {sub.is_active ? "Active" : "Inactive"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={() => { setEditing(sub); setShowForm(true); }}
                      aria-label="Edit"
                    >
                      <PencilLine className="h-3.5 w-3.5" />
                    </Button>
                    {sub.is_active ? (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => void handleDeactivate(sub)}
                        aria-label="Deactivate"
                        disabled={deactivateMutation.isPending}
                      >
                        <PowerOff className="h-3.5 w-3.5" />
                      </Button>
                    ) : (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-success hover:text-success"
                        onClick={() => void handleReactivate(sub)}
                        aria-label="Reactivate"
                        disabled={reactivateMutation.isPending}
                      >
                        <Power className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

// ── Top-level manager ────────────────────────────────────────────────────────

export function ActivityMasterManager() {
  const [showForm, setShowForm] = React.useState(false);
  const [editing, setEditing] = React.useState<ActivityMaster | null>(null);
  const [expanded, setExpanded] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");

  const query = useActivities(false);
  const deactivateMutation = useDeactivateActivity();
  const reactivateMutation = useReactivateActivity();

  const items = query.data ?? [];
  const filtered = items.filter((a) => a.name.toLowerCase().includes(search.toLowerCase()));

  function closeForm() {
    setEditing(null);
    setShowForm(false);
  }

  async function handleDeactivate(a: ActivityMaster) {
    try {
      await deactivateMutation.mutateAsync(a.id);
      toast.success(`"${a.name}" deactivated`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not deactivate.");
    }
  }

  async function handleReactivate(a: ActivityMaster) {
    try {
      await reactivateMutation.mutateAsync(a.id);
      toast.success(`"${a.name}" reactivated`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not reactivate.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <Input
          placeholder="Search activities…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
        {!showForm && (
          <Button size="sm" onClick={() => { setEditing(null); setShowForm(true); }}>
            <PlusCircle className="h-4 w-4" />
            New Activity
          </Button>
        )}
      </div>

      {showForm && <ActivityForm editing={editing} onDone={closeForm} />}

      <Card className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-8" />
              <TableHead className="w-28">Code</TableHead>
              <TableHead>Activity Name</TableHead>
              <TableHead className="w-24 text-center">Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!query.isLoading && filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No activities found.
                </TableCell>
              </TableRow>
            )}
            {filtered.map((a) => {
              const isExpanded = expanded === a.id;
              return (
                <React.Fragment key={a.id}>
                  <TableRow className={!a.is_active ? "opacity-50" : ""}>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-6 w-6"
                        onClick={() => setExpanded(isExpanded ? null : a.id)}
                        aria-label={isExpanded ? "Collapse" : "Expand"}
                      >
                        {isExpanded ? (
                          <ChevronDown className="h-3.5 w-3.5" />
                        ) : (
                          <ChevronRight className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </TableCell>
                    <TableCell className="font-mono text-sm">{a.code ?? "—"}</TableCell>
                    <TableCell className="font-medium">{a.name}</TableCell>
                    <TableCell className="text-center">
                      <Badge variant={a.is_active ? "success" : "neutral"} dot>
                        {a.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() => { setEditing(a); setShowForm(true); }}
                          aria-label="Edit"
                        >
                          <PencilLine className="h-3.5 w-3.5" />
                        </Button>
                        {a.is_active ? (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-destructive hover:text-destructive"
                            onClick={() => void handleDeactivate(a)}
                            aria-label="Deactivate"
                            disabled={deactivateMutation.isPending}
                          >
                            <PowerOff className="h-3.5 w-3.5" />
                          </Button>
                        ) : (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7 text-success hover:text-success"
                            onClick={() => void handleReactivate(a)}
                            aria-label="Reactivate"
                            disabled={reactivateMutation.isPending}
                          >
                            <Power className="h-3.5 w-3.5" />
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                  {isExpanded && (
                    <TableRow>
                      <TableCell colSpan={5} className="p-0">
                        <SubActivitiesPanel activity={a} />
                      </TableCell>
                    </TableRow>
                  )}
                </React.Fragment>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
