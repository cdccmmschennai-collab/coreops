"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { useActivityTypeOptions, useCreateActivityType } from "@/features/activity-types/hooks";
import { useAuth } from "@/features/auth/auth-provider";
import { useTasks } from "@/features/tasks/hooks";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { AppError } from "@/lib/api-client";
import { formatMinutes } from "@/lib/format";
import { can } from "@/lib/rbac";

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

export function WorkReportForm({ mode, defaultValues, reportId }: WorkReportFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);

  const { employeeId, role } = useAuth();
  const { byId: empById } = useEmployeeOptions();
  const { items: projects, byId: projById } = useProjectOptions();
  const { items: activityTypes } = useActivityTypeOptions();
  const createActivityType = useCreateActivityType();

  const employeeName = employeeId ? (empById.get(employeeId) ?? "—") : "—";
  const canCreateActivityType = can(role, "masterdata.manage");

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

  // Activity type combobox options — code shown on the right
  const activityOptions = React.useMemo(
    () =>
      activityTypes.map((a) => ({
        value: a.name,   // stored as TEXT in work_report_tasks.activity_type
        label: a.name,
        sublabel: a.code ?? undefined,
        keywords: [a.code ?? "", a.name, a.category],
      })),
    [activityTypes],
  );

  async function handleCreateActivityType(inputName: string) {
    try {
      await createActivityType.mutateAsync({
        name: inputName,
        category: "GENERAL",
        requires_project: false,
      });
      toast.success(`Activity type "${inputName}" created`);
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not create activity type.");
    }
  }

  const form = useForm<WorkReportFormValues>({
    resolver: zodResolver(workReportFormSchema),
    defaultValues,
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "tasks",
  });

  const createMutation = useCreateWorkReport();
  const updateMutation = useUpdateWorkReport(reportId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const watchedTasks = form.watch("tasks");
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

                      {/* Task hours — task-based work; adds to the day total */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.task_hours`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Task hours <span className="font-normal">(HH.MM)</span>
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
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
                              Duration <span className="font-normal">(HH.MM)</span>
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

                    {/* Row B: Activity Type (searchable) | Description | Tags | Docs | BOM | Spares */}
                    <div className="grid gap-2 sm:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)_repeat(4,5rem)]">

                      {/* Activity Type — searchable combobox; PM can create inline */}
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.activity_type`}
                        render={({ field: f }) => (
                          <FormItem>
                            <FormLabel className="text-xs text-muted-foreground">
                              Activity Type <span className="text-destructive">*</span>
                            </FormLabel>
                            <FormControl>
                              <Combobox
                                value={f.value || ""}
                                onValueChange={(v) => f.onChange(v)}
                                options={activityOptions}
                                placeholder="Select activity type…"
                                searchPlaceholder="Search by name or code…"
                                emptyMessage="No matching activity types."
                                allowClear={false}
                                allowCreate={canCreateActivityType}
                                onCreateNew={async (name) => {
                                  await handleCreateActivityType(name);
                                  f.onChange(name);
                                }}
                              />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />

                      {/* Day Remarks (optional) */}
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

                      {/* Count fields */}
                      {(
                        [
                          ["tags_count",   "Tags"],
                          ["docs_count",   "Docs"],
                          ["bom_count",    "BOM"],
                          ["spares_count", "Spares"],
                        ] as const
                      ).map(([name, label]) => (
                        <FormField
                          key={name}
                          control={form.control}
                          name={`tasks.${index}.${name}`}
                          render={({ field: f }) => (
                            <FormItem>
                              <FormLabel className="text-xs text-muted-foreground">
                                {label}
                              </FormLabel>
                              <FormControl>
                                <Input type="number" min={0} placeholder="0" {...f} />
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      ))}
                    </div>
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
