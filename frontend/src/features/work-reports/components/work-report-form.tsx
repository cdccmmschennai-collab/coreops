"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Combobox } from "@/components/ui/combobox";
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
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import { useActivities, useSubActivityOptions } from "@/features/activity-master/hooks";
import { useAuth } from "@/features/auth/auth-provider";
import { useTasks } from "@/features/tasks/hooks";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { AppError } from "@/lib/api-client";
import { formatInt, formatMinutes } from "@/lib/format";

import { useCreateWorkReport, useUpdateWorkReport } from "../hooks";
import { useProjectOptions } from "../project-options";
import {
  DAY_STATUS_LABEL,
  DAY_STATUSES,
  EMPTY_TASK_ROW,
  WORK_LOCATION_LABEL,
  WORK_LOCATIONS,
  hoursToMinutes,
  toCreateBody,
  toUpdateBody,
  workReportFormSchema,
  type WorkReportFormValues,
} from "../schemas";

interface WorkReportFormProps {
  mode: "create" | "edit";
  defaultValues: WorkReportFormValues;
  reportId?: string;
}

/** "2026-06-16" + 2 -> "2026-06-18". Client-side preview only, for a
 * TASK_BASED row that hasn't been saved yet — the server is authoritative
 * once the row exists (it computes due_date the same way, on save). */
function addDays(isoDate: string, days: number): string | null {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

export function WorkReportForm({ mode, defaultValues, reportId }: WorkReportFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);

  const { employeeId } = useAuth();
  const { byId: empById } = useEmployeeOptions();
  const { items: projects, byId: projById } = useProjectOptions();
  const { data: activities } = useActivities(true);
  const { items: subActivities, byId: subActivityById } = useSubActivityOptions();

  const employeeName = employeeId ? (empById.get(employeeId) ?? "—") : "—";

  // Project combobox options — RBAC list + ghost entries for projects in
  // existing tasks that are no longer accessible (archived / membership lost).
  // Ghost entries are display-only; the backend still validates on submit.
  const projectOptions = React.useMemo(() => {
    const base = projects.map((p) => ({
      value: p.id,
      label: p.name,
      sublabel: p.code,
      description: p.client ?? undefined,
      keywords: [p.code, p.name, p.client ?? "", p.job_code_code ?? ""],
    }));
    if (mode !== "edit") return base;
    const inList = new Set(projects.map((p) => p.id));
    const ghosts: (typeof base)[0][] = [];
    const seen = new Set<string>();
    for (const t of defaultValues.tasks) {
      if (t.project_id && !inList.has(t.project_id) && t.project_name && !seen.has(t.project_id)) {
        seen.add(t.project_id);
        ghosts.push({
          value: t.project_id,
          label: t.project_name,            // string (narrowed by if guard)
          sublabel: t.project_code ?? "",   // string (coerce undefined → "")
          description: undefined,
          keywords: [t.project_code ?? "", t.project_name],
        });
      }
    }
    return [...base, ...ghosts];
  }, [projects, mode, defaultValues.tasks]);

  // The author's own assigned tasks (open / in-progress) for the task picker.
  const { data: myTasksData } = useTasks({
    mine: true, q: "", status: "", priority: "", limit: 100, offset: 0,
  });
  const myTaskById = React.useMemo(
    () => new Map((myTasksData?.items ?? []).map((t) => [t.id, t])),
    [myTasksData],
  );
  const taskOptions = React.useMemo(
    () =>
      (myTasksData?.items ?? [])
        // Show assignable tasks incl. completed (you still log hours for them);
        // only cancelled tasks are hidden.
        .filter((t) => t.status !== "cancelled")
        .map((t) => ({
          value: t.id,
          label: t.title,
          sublabel: t.project_name ?? undefined,
          keywords: [t.title, t.project_name ?? ""],
        })),
    [myTasksData],
  );

  // Activity Master combobox options (Activity → Sub-Activity cascade).
  const activityOptions = React.useMemo(
    () => (activities ?? []).map((a) => ({ value: a.id, label: a.name })),
    [activities],
  );
  const subActivityOptionsByActivity = React.useMemo(() => {
    const map = new Map<string, { value: string; label: string }[]>();
    for (const s of subActivities) {
      const list = map.get(s.activity_id) ?? [];
      list.push({ value: s.id, label: s.name });
      map.set(s.activity_id, list);
    }
    return map;
  }, [subActivities]);

  const form = useForm<WorkReportFormValues>({
    resolver: zodResolver(workReportFormSchema),
    defaultValues,
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "tasks",
  });

  // Backfill the UI-only `activity_id` filter for rows loaded from the API
  // with a sub_activity_id already set (edit mode) — once the flat
  // sub-activity options arrive, resolve which Activity each belongs to so
  // the Sub-Activity select shows the right filtered list immediately.
  React.useEffect(() => {
    if (subActivityById.size === 0) return;
    fields.forEach((_, index) => {
      const row = form.getValues(`tasks.${index}`);
      if (row.sub_activity_id && !row.activity_id) {
        const sub = subActivityById.get(row.sub_activity_id);
        if (sub) form.setValue(`tasks.${index}.activity_id`, sub.activity_id);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subActivityById, fields.length]);

  const createMutation = useCreateWorkReport();
  const updateMutation = useUpdateWorkReport(reportId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const watchedTasks = form.watch("tasks");
  const reportDate = form.watch("report_date");
  const totalMinutes = (watchedTasks ?? []).reduce(
    (sum, t) =>
      sum + (hoursToMinutes(t?.duration_hours) ?? 0) + (hoursToMinutes(t?.task_hours) ?? 0),
    0,
  );

  const tasksError = form.formState.errors.tasks?.message;

  async function onSubmit(values: WorkReportFormValues) {
    setFormError(null);
    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Draft saved" : "Changes saved");
      router.push(`/work-reports/${result.id}`);
    } catch (error) {
      setFormError(
        error instanceof AppError ? error.message : "Something went wrong. Please try again.",
      );
    }
  }

  return (
    <Card>
      <CardContent className="pt-6">
        {formError && (
          <div
            role="alert"
            className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          >
            {formError}
          </div>
        )}
        <Form {...form}>
          <form className="space-y-6" onSubmit={form.handleSubmit(onSubmit)} noValidate>

            {/* ── Employee (read-only) ── */}
            <div className="flex items-center gap-3 rounded-md border border-border bg-muted/40 px-3 py-2 text-sm">
              <span className="text-muted-foreground">Submitting as:</span>
              <span className="font-medium">{employeeName}</span>
            </div>

            {/* ── Row 1: Date, Day Status, Location ── */}
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField
                control={form.control}
                name="report_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Date <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="date" {...field} disabled={mode === "edit"} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="day_status"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Day Status <span className="text-destructive">*</span>
                    </FormLabel>
                    <Select
                      value={field.value ?? undefined}
                      onValueChange={(v) => field.onChange(v)}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select status" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {DAY_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {DAY_STATUS_LABEL[s]}
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
                name="location"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Office Location <span className="text-destructive">*</span>
                    </FormLabel>
                    <Select
                      value={field.value ?? undefined}
                      onValueChange={(v) => field.onChange(v)}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select location" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {WORK_LOCATIONS.map((l) => (
                          <SelectItem key={l} value={l}>
                            {WORK_LOCATION_LABEL[l]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <Separator />

            {/* ── Project Task Rows ── */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Project activities</h3>
                {totalMinutes > 0 && (
                  <span className="text-sm text-muted-foreground">
                    Total:{" "}
                    <span className="tabular font-medium">{formatMinutes(totalMinutes)}</span>
                  </span>
                )}
              </div>

              {fields.map((field, index) => {
                const selectedProjectId = watchedTasks?.[index]?.project_id;
                const selectedProject = selectedProjectId
                  ? projById.get(selectedProjectId)
                  : undefined;
                // Prefer the live RBAC-scoped project; fall back to the task snapshot
                // (edit mode where the project is archived / no longer accessible).
                const projectCodeLabel =
                  selectedProject?.code ?? watchedTasks?.[index]?.project_code ?? "—";
                const jobCodeLabel = selectedProject?.job_code_code ?? "—";

                return (
                  <div
                    key={field.id}
                    className="space-y-2 rounded-lg border border-border p-3"
                  >
                    {/* Task line shares Row A's grid so Task hours lands in the same
                        column as Duration (the two hour fields stack one above the
                        other); picking a task fills in the project. */}
                    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-[minmax(0,1.4fr)_120px_120px_110px_40px]">
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.task_id`}
                        render={({ field: f }) => (
                          <FormItem className="md:col-span-3">
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Task <span className="font-normal">(optional)</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value || ""}
                                onValueChange={(v) => {
                                  f.onChange(v);
                                  const t = v ? myTaskById.get(v) : undefined;
                                  if (t?.project_id) {
                                    form.setValue(
                                      `tasks.${index}.project_id`,
                                      t.project_id,
                                      { shouldValidate: true },
                                    );
                                  }
                                }}
                                options={taskOptions}
                                placeholder="Select an assigned task…"
                                searchPlaceholder="Search your tasks…"
                                emptyMessage="No tasks assigned to you."
                                allowClear
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {/* Hours (task-based work; adds to the day total) — kept short
                          ("Hours" not "Task hours") so the label stays on one line
                          and this box aligns with the row below it. */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.task_hours`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormLabel className="block whitespace-nowrap text-xs leading-none text-muted-foreground">
                              Hours <span className="font-normal">(HH.MM)</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                type="text"
                                inputMode="decimal"
                                placeholder="e.g. 2.30"
                                {...f}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>

                    {/* Row A — one grid; columns collapse responsively:
                          desktop → Name | Code | Job | Duration | Actions on one row.
                        Duration here = project-based hours (distinct from Task hours). */}
                    <div className="grid grid-cols-1 items-start gap-3 md:grid-cols-[minmax(0,1.4fr)_120px_120px_110px_40px]">

                      {/* Project Name — searchable combobox (name + code) */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.project_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Project Name <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value}
                                onValueChange={f.onChange}
                                options={projectOptions}
                                placeholder="Select project…"
                                searchPlaceholder="Search by name or code…"
                                emptyMessage="No matching projects."
                                allowClear={false}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {/* Project Code — read-only metadata, auto-filled from selection */}
                      <div className="space-y-2">
                        <span className="block text-xs font-medium leading-none text-muted-foreground">
                          Project Code
                        </span>
                        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                          {projectCodeLabel}
                        </div>
                      </div>

                      {/* Job Code — read-only metadata, auto-filled from selection */}
                      <div className="space-y-2">
                        <span className="block text-xs font-medium leading-none text-muted-foreground">
                          Job Code
                        </span>
                        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
                          {jobCodeLabel}
                        </div>
                      </div>

                      {/* Duration — project-based hours (decimals allowed) */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.duration_hours`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormLabel className="block whitespace-nowrap text-xs leading-none text-muted-foreground">
                              Duration <span className="font-normal">(HH.MM)</span> <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Input
                                type="text"
                                inputMode="decimal"
                                placeholder="e.g. 2.30"
                                {...f}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {/* Actions — delete. A spacer label (desktop only) keeps the
                          button on the input baseline via the grid, not margins. */}
                      <div className="flex flex-col gap-2 items-start md:items-start">
                        <span
                          className="hidden text-xs font-medium leading-none md:block"
                          aria-hidden
                        >
                          &nbsp;
                        </span>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => remove(index)}
                          disabled={fields.length === 1}
                          aria-label="Remove activity"
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>

                    {/* Row B: Activity (25%) | Sub-Activity (75%) — own full-width row
                        so long sub-activity names show in full, uncramped. Selections
                        come from the Activity Master (Settings → Activity Master),
                        never hardcoded here. */}
                    <div className="grid grid-cols-[1fr_3fr] gap-2">
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.activity_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="text-xs text-muted-foreground">
                              Activity <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value || ""}
                                onValueChange={(v) => {
                                  f.onChange(v);
                                  // Changing the Activity invalidates any previously
                                  // chosen Sub-Activity from a different Activity.
                                  const currentSub = form.getValues(`tasks.${index}.sub_activity_id`);
                                  if (currentSub && subActivityById.get(currentSub)?.activity_id !== v) {
                                    form.setValue(`tasks.${index}.sub_activity_id`, "");
                                    form.setValue(`tasks.${index}.sub_activity_name`, undefined);
                                    form.setValue(`tasks.${index}.activity_name`, undefined);
                                  }
                                }}
                                options={activityOptions}
                                placeholder="Select activity…"
                                searchPlaceholder="Search activities…"
                                emptyMessage="No matching activities."
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.sub_activity_id`}
                        render={({ field: f }) => {
                          const selectedActivityId = watchedTasks?.[index]?.activity_id;
                          const options = selectedActivityId
                            ? subActivityOptionsByActivity.get(selectedActivityId) ?? []
                            : [];
                          return (
                            <FormItem className="min-w-0">
                              <FormLabel className="text-xs text-muted-foreground">
                                Sub-Activity <span className="text-destructive">*</span>
                              </FormLabel>
                              <FormControl>
                                <Combobox
                                  value={f.value || ""}
                                  onValueChange={(v) => {
                                    f.onChange(v);
                                    const sub = v ? subActivityById.get(v) : undefined;
                                    form.setValue(`tasks.${index}.sub_activity_name`, sub?.name);
                                    form.setValue(`tasks.${index}.activity_name`, sub?.activity_name);
                                    // Server derives activity_type from the new selection.
                                    form.setValue(`tasks.${index}.activity_type`, "");
                                  }}
                                  options={options}
                                  placeholder={selectedActivityId ? "Select sub-activity…" : "Pick an Activity first"}
                                  searchPlaceholder="Search sub-activities…"
                                  emptyMessage="No matching sub-activities."
                                  disabled={!selectedActivityId}
                                />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          );
                        }}
                      />
                    </div>

                    {/* Row B2: Day Remarks — own full-width row, right below Activity. */}
                    <FormField
                      control={form.control}
                      name={`tasks.${index}.description`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-muted-foreground">
                            Day Remarks (optional)
                          </FormLabel>
                          <FormControl>
                            <Input placeholder="What did you work on?" {...f} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

                    {/* Row B3: Tags / Docs / BOM / Spares — operational reporting,
                        independent of the benchmark target shown on whichever field
                        is relevant. None are required. Same full-row 4-col grid as
                        "Maintenance counts" below, so the layout stays consistent
                        regardless of label length (e.g. "Docs (Target: 1000/1d)"). */}
                    <div className="grid gap-3 sm:grid-cols-4">
                      {(() => {
                        const subId = watchedTasks?.[index]?.sub_activity_id;
                        const sub = subId ? subActivityById.get(subId) : undefined;
                        // The benchmark target is shown directly on whichever count
                        // field the sub-activity names — there is no separate
                        // "Actual Count" entry, so the same number is never typed twice.
                        const targetField = sub?.benchmark_type === "NUMERIC" ? sub.relevant_count_field : null;

                        return (
                          [
                            ["tags_count",   "Tags",   "tags"],
                            ["docs_count",   "Docs",   "docs"],
                            ["bom_count",    "BOM",    "bom"],
                            ["spares_count", "Spares", "spares"],
                          ] as const
                        ).map(([name, label, countField]) => {
                          const isTarget = targetField === countField;
                          return (
                            <FormField
                              key={name}
                              control={form.control}
                              name={`tasks.${index}.${name}`}
                              render={({ field: f }) => (
                                <FormItem>
                                  <FormLabel
                                    className={
                                      isTarget
                                        ? "text-xs font-medium text-foreground"
                                        : "text-xs text-muted-foreground"
                                    }
                                  >
                                    {label}
                                    {isTarget && (
                                      <span className="font-normal text-muted-foreground">
                                        {" "}(Target: {formatInt(sub!.benchmark_value)}/{sub!.benchmark_period_days ?? 1}d)
                                      </span>
                                    )}
                                  </FormLabel>
                                  <FormControl>
                                    <Input
                                      type="number"
                                      min={0}
                                      placeholder="0"
                                      className={isTarget ? "border-primary" : undefined}
                                      {...f}
                                    />
                                  </FormControl>
                                  <FormMessage />
                                </FormItem>
                              )}
                            />
                          );
                        });
                      })()}
                    </div>

                    {/* Row C: TASK_BASED sub-activities only — a single
                        completion checkbox. No status dropdown, no manual
                        date entry: started_date/due_date/completed_date are
                        all system-managed (see schemas.ts). NUMERIC
                        sub-activities have no extra row here: the benchmark
                        target is shown directly on the matching count field
                        above (Tags/Docs/BOM/Spares), not a separate entry. */}
                    {(() => {
                      const subId = watchedTasks?.[index]?.sub_activity_id;
                      const sub = subId ? subActivityById.get(subId) : undefined;
                      if (sub?.benchmark_type !== "TASK_BASED") return null;

                      const row = watchedTasks?.[index];
                      // Prefer the server-computed due_date (existing row);
                      // for a brand-new row not yet saved, preview it
                      // client-side from the report date + allocated duration.
                      const periodDays = sub.benchmark_period_days ?? 1;
                      const previewDue = row?.due_date
                        ? row.due_date
                        : reportDate
                          ? addDays(reportDate, periodDays)
                          : null;

                      return (
                        <FormField
                          control={form.control}
                          name={`tasks.${index}.is_completed`}
                          render={({ field: f }) => (
                            <FormItem>
                              <label className="flex items-center gap-2 text-sm">
                                <FormControl>
                                  <Checkbox
                                    checked={f.value}
                                    onChange={(e) => f.onChange(e.target.checked)}
                                  />
                                </FormControl>
                                <span>Task Completed</span>
                                <span className="text-xs text-muted-foreground">
                                  (within {periodDays}d
                                  {previewDue ? ` — due ${previewDue}` : ""})
                                </span>
                              </label>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      );
                    })()}
                  </div>
                );
              })}

              {tasksError && (
                <p className="text-xs font-medium text-destructive">{tasksError}</p>
              )}

              <Button
                type="button"
                variant="secondary"
                onClick={() => append({ ...EMPTY_TASK_ROW })}
              >
                <Plus className="h-4 w-4" />
                Add activity
              </Button>
            </div>

            <Separator />

            {/* ── Well Head, PM Plant ── */}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="well_head_no"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Well Head No.{" "}
                      <span className="font-normal text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="If worked on well head" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="pm_plant"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      PM Plant{" "}
                      <span className="font-normal text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="PM plant identifier" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* ── Maintenance Counters ── */}
            <div>
              <p className="mb-2 text-sm font-medium">Maintenance counts</p>
              <div className="grid gap-3 sm:grid-cols-4">
                {(
                  [
                    ["task_list_count",        "Task List"],
                    ["task_list_op_count",     "Task List Ops"],
                    ["maintenance_item_count", "Maint. Items"],
                    ["maintenance_plan_count", "Maint. Plans"],
                  ] as const
                ).map(([name, label]) => (
                  <FormField
                    key={name}
                    control={form.control}
                    name={name}
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel className="text-xs">{label}</FormLabel>
                        <FormControl>
                          <Input type="number" min={0} placeholder="0" {...field} />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                ))}
              </div>
            </div>

            <Separator />

            {/* ── Query / Issues (end) ── */}
            <FormField
              control={form.control}
              name="query_text"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Query / Issues{" "}
                    <span className="font-normal text-muted-foreground">(optional)</span>
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Any blockers or questions?"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                variant="ghost"
                onClick={() => router.back()}
                disabled={isPending}
              >
                Cancel
              </Button>
              <Button type="submit" loading={isPending}>
                {mode === "create" ? "Save Draft" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
