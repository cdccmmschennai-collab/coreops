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
import { Tabs } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { AppError } from "@/lib/api-client";
import { formatInt } from "@/lib/format";
import { ActivityAccessBadge } from "@/features/activity-access/components/activity-access-badge";
import { ActivityAccessTab } from "@/features/activity-access/components/activity-access-tab";

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
import {
  ALL_BENCHMARK_TYPES,
  BENCHMARK_TYPE_LABEL,
  COUNT_FIELDS,
  COUNT_FIELD_LABEL,
  SELECTABLE_BENCHMARK_TYPES,
  isQuantityBenchmark,
  isTaskBenchmark,
} from "../types";
import type { ActivityMaster, BenchmarkType, RelevantCountField } from "../types";

const NONE = "__none__";
// BENCHMARK_TYPE_LABEL / COUNT_FIELD_LABEL / COUNT_FIELDS and the mode-set
// helpers all come from ../types — one declaration shared with the report form,
// mirroring the backend's own sets.
//
// SELECTABLE_BENCHMARK_TYPES offers only the three current modes. The legacy
// NUMERIC / TASK_BASED remain valid, keep working, and still render a readable
// label on existing records — they are simply not offered for new ones.
const BENCHMARK_TYPES = SELECTABLE_BENCHMARK_TYPES;

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
    // Validates against ALL modes (a legacy record must load and re-save); the
    // dropdown separately narrows to the three offered for new configuration.
    benchmark_type: z.union([z.enum(ALL_BENCHMARK_TYPES), z.literal(NONE)]),
    benchmark_value: z.string().optional().default(""),
    benchmark_period_days: z.string().optional().default(""),
    benchmark_unit_note: z.string().trim().max(100).optional().default(""),
    benchmark_remarks: z.string().trim().max(500).optional().default(""),
    relevant_count_field: z.union([z.enum(COUNT_FIELDS), z.literal(NONE)]),
  })
  .superRefine((v, ctx) => {
    if (v.benchmark_type === NONE) return;
    const type = v.benchmark_type as BenchmarkType;
    // Mirrors the backend's DB constraints exactly: every QUANTITY mode needs a
    // target and a measurement unit; every TASK mode needs a period to compute
    // its due date from. TASK_WITH_QUANTITY is both, so it needs all three.
    if (isQuantityBenchmark(type)) {
      if (!v.benchmark_value.trim()) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Required — this benchmark measures a quantity",
          path: ["benchmark_value"],
        });
      }
      if (v.relevant_count_field === NONE) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Required — this is the field the benchmark reads as the actual value",
          path: ["relevant_count_field"],
        });
      }
    }
    if (isTaskBenchmark(type)) {
      const days = Number(v.benchmark_period_days);
      if (!v.benchmark_period_days.trim() || !Number.isFinite(days) || days < 1) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          message: "Required — the task's allocated duration in days (minimum 1)",
          path: ["benchmark_period_days"],
        });
      }
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
  const typeOrNull = benchmarkType === NONE ? null : (benchmarkType as BenchmarkType);
  // Which fields the chosen mode actually needs. TASK_WITH_QUANTITY is both, so
  // it shows target + unit + period together.
  const showQuantityFields = isQuantityBenchmark(typeOrNull);
  const showTaskFields = isTaskBenchmark(typeOrNull);
  const isLegacyType =
    typeOrNull != null &&
    !(SELECTABLE_BENCHMARK_TYPES as readonly string[]).includes(typeOrNull);

  async function onSubmit(values: SubActivityFormValues) {
    const type = values.benchmark_type === NONE ? null : values.benchmark_type;
    // A quantity mode is the only thing that gives the target and unit meaning:
    // switching a record to a status-only task must not leave a stale 500/pages
    // behind for the benchmark to pick up.
    const carriesQuantity = isQuantityBenchmark(type);
    const body = {
      code: values.code || null,
      name: values.name,
      benchmark_type: type,
      benchmark_value:
        carriesQuantity && values.benchmark_value.trim()
          ? Number(values.benchmark_value)
          : null,
      benchmark_period_days: values.benchmark_period_days.trim()
        ? Number(values.benchmark_period_days)
        : null,
      benchmark_unit_note: values.benchmark_unit_note || null,
      benchmark_remarks: values.benchmark_remarks || null,
      relevant_count_field:
        carriesQuantity && values.relevant_count_field !== NONE
          ? values.relevant_count_field
          : null,
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
                        {/* An existing record on a legacy mode keeps its value
                            readable and selectable-back; legacy modes are never
                            offered to records that don't already use one. */}
                        {isLegacyType && (
                          <SelectItem value={benchmarkType}>
                            {BENCHMARK_TYPE_LABEL[benchmarkType as BenchmarkType]}
                          </SelectItem>
                        )}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {showQuantityFields && (
                <FormField
                  control={form.control}
                  name="benchmark_value"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>
                        Target quantity <span className="text-destructive">*</span>
                      </FormLabel>
                      <FormControl>
                        <Input {...field} inputMode="decimal" placeholder="e.g. 500" />
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
                      <FormLabel>
                        Period (days)
                        {showTaskFields && <span className="text-destructive"> *</span>}
                      </FormLabel>
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
                {showQuantityFields && (
                  <FormField
                    control={form.control}
                    name="relevant_count_field"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>
                          Measurement unit <span className="text-destructive">*</span>
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
    <div className="space-y-3 p-4">
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
                  {/* Quantity modes show target/period/unit; a status-only task
                      has no quantity to show. Driven by the shared mode sets, so
                      legacy NUMERIC/TASK_BASED records render correctly too. */}
                  {isQuantityBenchmark(sub.benchmark_type) &&
                    `${formatInt(sub.benchmark_value)} / ${sub.benchmark_period_days ?? 1}d` +
                    (sub.relevant_count_field
                      ? ` (${COUNT_FIELD_LABEL[sub.relevant_count_field].toUpperCase()})`
                      : "")}
                  {isTaskBenchmark(sub.benchmark_type) && (
                    <span className="block text-xs text-muted-foreground">
                      {isQuantityBenchmark(sub.benchmark_type)
                        ? "Task - quantity, duration and completion"
                        : "Task - duration and completion"}
                    </span>
                  )}
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

// ── Expanded activity row: Sub-Activities / Access tabs ─────────────────────

function ExpandedActivityPanel({ activity }: { activity: ActivityMaster }) {
  // Sub-Activities stays the default so existing behaviour is preserved; the
  // Access tab (and its network request) only mounts when the PM opens it.
  const [tab, setTab] = React.useState<"sub" | "access">("sub");
  return (
    <div className="border-t border-border bg-muted/30">
      <div className="px-4 pt-3">
        <Tabs
          value={tab}
          onChange={(v) => setTab(v as "sub" | "access")}
          items={[
            { value: "sub", label: "Sub-Activities" },
            { value: "access", label: "Access" },
          ]}
        />
      </div>
      {tab === "sub" ? (
        <SubActivitiesPanel activity={activity} />
      ) : (
        <ActivityAccessTab activity={activity} />
      )}
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

  // The activity form always renders at the top of this panel. Editing a row far
  // down the table would otherwise open the form off-screen; bring it into view
  // whenever the form opens (or the edit target changes) so the PM sees it.
  const topRef = React.useRef<HTMLDivElement>(null);
  React.useEffect(() => {
    if (showForm) {
      topRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [showForm, editing]);

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
      <div ref={topRef} className="flex items-center justify-between gap-3">
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
              <TableHead className="w-32 text-center">Access</TableHead>
              <TableHead className="w-24 text-center">Status</TableHead>
              <TableHead className="w-24" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.isLoading && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            )}
            {!query.isLoading && filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground">
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
                      <ActivityAccessBadge accessType={a.access_type} />
                    </TableCell>
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
                      <TableCell colSpan={6} className="p-0">
                        <ExpandedActivityPanel activity={a} />
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
