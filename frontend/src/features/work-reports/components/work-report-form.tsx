"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm, type Control } from "react-hook-form";
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
import { useMaintenancePlantOptions } from "@/features/plant-master/hooks";
import { useTasks } from "@/features/tasks/hooks";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { AppError } from "@/lib/api-client";
import { formatInt } from "@/lib/format";

import { useCreateWorkReport, useUpdateWorkReport, useWorkReportList } from "../hooks";
import { useProjectOptions } from "../project-options";
import {
  DAY_STATUS_LABEL,
  DAY_STATUSES,
  EMPTY_TASK_ROW,
  WORK_LOCATION_LABEL,
  WORK_LOCATIONS,
  isNoActivityDayStatus,
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

const COUNT_FIELD_KEY = {
  tags: "tags_count",
  docs: "docs_count",
  bom: "bom_count",
  spares: "spares_count",
} as const;

/** "2026-06-16" + 2 -> "2026-06-18". Client-side preview only, for a
 * TASK_BASED row that hasn't been saved yet — the server is authoritative
 * once the row exists (it computes due_date the same way, on save). */
function addDays(isoDate: string, days: number): string | null {
  const d = new Date(`${isoDate}T00:00:00`);
  if (Number.isNaN(d.getTime())) return null;
  d.setDate(d.getDate() + days);
  // Format from local parts (not toISOString, which would shift the day by the
  // UTC offset and land a day early in IST).
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/**
 * Maintenance Plant picker for one task row. The options are scoped to the
 * selected project's Planning Plant — the dropdown reloads (a fresh,
 * planning-plant-filtered fetch) whenever that code changes, so a user never
 * sees Maintenance Plants from other Planning Plants. Planning Plant +
 * Description (PP) are determined by the project and shown read-only.
 */
function MaintenancePlantField({
  control,
  index,
  planningPlantCode,
  planningPlantDescription,
}: {
  control: Control<WorkReportFormValues>;
  index: number;
  planningPlantCode?: string;
  planningPlantDescription?: string;
}) {
  const hasPlanningPlant = !!planningPlantCode;
  const { options, isLoading } = useMaintenancePlantOptions(
    true,
    planningPlantCode,
    hasPlanningPlant,
  );

  return (
    <>
      <FormField
        control={control}
        name={`tasks.${index}.maintenance_plant_id`}
        render={({ field: f }) => (
          <FormItem className="min-w-0">
            <FormLabel className="block text-xs font-medium leading-none text-muted-foreground">
              Maintenance Plant
            </FormLabel>
            <FormControl>
              <Combobox
                value={f.value || ""}
                onValueChange={f.onChange}
                options={options}
                placeholder={
                  hasPlanningPlant
                    ? isLoading
                      ? "Loading plants…"
                      : "Select plant…"
                    : "Select a project first"
                }
                searchPlaceholder="Search maintenance plants…"
                emptyMessage="No plants for this Planning Plant."
                disabled={!hasPlanningPlant}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Planning Plant
        </span>
        <div className="flex h-9 items-center rounded-md border border-input bg-muted/40 px-3 font-mono text-sm text-muted-foreground">
          {planningPlantCode ?? "—"}
        </div>
      </div>
      <div className="space-y-2">
        <span className="block text-xs font-medium leading-none text-muted-foreground">
          Description (PP)
        </span>
        <div className="flex h-9 items-center truncate rounded-md border border-input bg-muted/40 px-3 text-sm text-muted-foreground">
          {planningPlantDescription ?? "—"}
        </div>
      </div>
    </>
  );
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
  const { fields, append, remove, replace } = useFieldArray({
    control: form.control,
    name: "tasks",
  });

  // Leave-type day statuses (week off / leave / company holiday / comp-off):
  // the employee did no project work, so the activity editor is frozen out —
  // no rows, no benchmark, no pending — and only Remarks + Query stay active.
  const dayStatus = form.watch("day_status");
  const noActivity = isNoActivityDayStatus(dayStatus);
  const prevNoActivity = React.useRef(noActivity);
  React.useEffect(() => {
    if (noActivity === prevNoActivity.current) return;
    prevNoActivity.current = noActivity;
    if (noActivity) {
      // Drop activity rows + clear Office Location — none of it applies on leave.
      replace([]);
      form.setValue("location", undefined, { shouldValidate: true });
    } else if (form.getValues("tasks").length === 0) {
      // Switched back to a working day with no rows — restore one empty row.
      replace([{ ...EMPTY_TASK_ROW }]);
    }
  }, [noActivity, replace, form]);

  // Backfill the UI-only `activity_id` filter for rows loaded from the API
  // with a sub_activity_id already set (edit mode) — once the flat
  // sub-activity options arrive, resolve which Activity each belongs to so
  // the Sub-Activity select shows the right filtered list immediately.
  React.useEffect(() => {
    if (subActivityById.size === 0) return;
    fields.forEach((_, index) => {
      const row = form.getValues(`tasks.${index}`);
      // `fields` can be momentarily out of sync with form values (e.g. right
      // after the task rows are cleared for a leave-type day) — skip if so.
      if (!row) return;
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

  // Reset a row's Maintenance Plant selection (and its derived snapshots) —
  // called whenever the row's project changes, since the available plants are
  // scoped to the new project's Planning Plant.
  const clearRowPlant = React.useCallback(
    (index: number) => {
      form.setValue(`tasks.${index}.maintenance_plant_id`, "");
      form.setValue(`tasks.${index}.planning_plant_code`, undefined);
      form.setValue(`tasks.${index}.planning_plant_description`, undefined);
    },
    [form],
  );

  // One report per employee per day: in create mode, look up whether the
  // selected date already has a report (backend also enforces this with a
  // unique constraint / 409). When one exists we surface a notice with a link
  // to open it, rather than letting the author create a duplicate.
  const existingForDate = useWorkReportList(
    {
      employee_id: employeeId ?? "",
      project_id: "",
      status: "",
      from: reportDate,
      to: reportDate,
      limit: 1,
      offset: 0,
    },
    { enabled: mode === "create" && !!employeeId && !!reportDate },
  );
  // Only trust a freshly-resolved result for the *current* date — never the
  // loading placeholder (which still holds the previous date's rows), so a date
  // with no report never trips the notice while its query is in flight.
  const existingReportForDate =
    mode === "create" && existingForDate.isSuccess && !existingForDate.isPlaceholderData
      ? existingForDate.data.items.find((r) => r.report_date === reportDate)
      : undefined;

  // Editable reports (draft / sent back / edit-granted) open straight in the
  // editor to add/edit activities; a locked report opens read-only, where the
  // author can still Request edit.
  const EDITABLE_STATUSES = ["draft", "rejected", "granted"];
  const pathForExisting = (r: { id: string; status: string }) =>
    EDITABLE_STATUSES.includes(r.status)
      ? `/work-reports/${r.id}/edit`
      : `/work-reports/${r.id}`;

  const tasksError = form.formState.errors.tasks?.message;

  async function onSubmit(values: WorkReportFormValues) {
    setFormError(null);

    // A NUMERIC sub-activity's relevant_count_field is the benchmark's
    // actual-value source — it must be filled in (not left at the default
    // 0) whenever that benchmark applies, so the deficit/productivity calc
    // at submit time reflects real production, not an unfilled field.
    let hasBenchmarkError = false;
    values.tasks.forEach((t, i) => {
      const sub = t.sub_activity_id ? subActivityById.get(t.sub_activity_id) : undefined;
      const countField = sub?.benchmark_type === "NUMERIC" ? sub.relevant_count_field : null;
      const key = countField ? COUNT_FIELD_KEY[countField] : null;
      if (key && Number(t[key] || 0) <= 0) {
        form.setError(`tasks.${i}.${key}`, {
          message: `Required — ${sub!.name} has a benchmark target`,
        });
        hasBenchmarkError = true;
      }
    });
    if (hasBenchmarkError) {
      setFormError("Fill in the required benchmark count(s) highlighted below.");
      return;
    }

    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Draft saved" : "Changes saved");
      router.push(`/work-reports/${result.id}`);
    } catch (error) {
      // Safety net: if the date was claimed between load and submit, the
      // backend returns 409 — open the existing report rather than dead-ending.
      if (mode === "create" && error instanceof AppError && error.status === 409) {
        const found = existingForDate.data?.items.find((r) => r.report_date === values.report_date);
        if (found) {
          toast.info(`A report for ${values.report_date} already exists — opening it.`);
          router.replace(pathForExisting(found));
          return;
        }
      }
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
        {existingReportForDate && (
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-md border border-primary/30 bg-primary/10 px-3 py-2 text-sm">
            <span>
              You already have a{" "}
              {existingReportForDate.status === "draft" ? "draft report" : "report"} for{" "}
              <span className="font-medium">{reportDate}</span>. Only one report per day is allowed —
              open it to add or edit activities.
            </span>
            <Button
              type="button"
              size="sm"
              onClick={() => router.push(pathForExisting(existingReportForDate))}
            >
              Open report
            </Button>
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
                      Office Location{" "}
                      {noActivity ? (
                        <span className="font-normal text-muted-foreground">(n/a)</span>
                      ) : (
                        <span className="text-destructive">*</span>
                      )}
                    </FormLabel>
                    <Select
                      value={field.value ?? undefined}
                      onValueChange={(v) => field.onChange(v)}
                      disabled={noActivity}
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
              <h3 className="text-sm font-medium">Project activities</h3>

              {noActivity ? (
                <div className="rounded-lg border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                  <p className="font-medium text-foreground">
                    No project activities for this day
                  </p>
                  <p className="mt-1">
                    You selected{" "}
                    <span className="font-medium">
                      {dayStatus ? DAY_STATUS_LABEL[dayStatus] : ""}
                    </span>{" "}
                    - you&apos;re off, so activities, benchmarks and pending tracking
                    don&apos;t apply. Add any Remarks or a Query below if needed.
                  </p>
                </div>
              ) : (
                <>
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
                    className="space-y-5 rounded-lg border border-border p-4"
                  >
                    {/* Task picker (optional — picking it fills in the project)
                        with the row's remove control on the same line. */}
                    <div className="flex items-end gap-2">
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.task_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0 flex-1">
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
                                    const current = form.getValues(`tasks.${index}.project_id`);
                                    form.setValue(
                                      `tasks.${index}.project_id`,
                                      t.project_id,
                                      { shouldValidate: true },
                                    );
                                    // Picking a task can switch the project (and thus
                                    // its Planning Plant) — clear the stale plant.
                                    if (current !== t.project_id) clearRowPlant(index);
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

                    {/* Row A — Project Name | Project Code | Job Code.
                        Project Code / Job Code are read-only, auto-filled from the
                        selected project. */}
                    <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_120px]">

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
                                onValueChange={(v) => {
                                  const changed = v !== f.value;
                                  f.onChange(v);
                                  // Maintenance Plant options depend on the project's
                                  // Planning Plant — clear any prior selection so a
                                  // plant from the old Planning Plant can't linger.
                                  if (changed) clearRowPlant(index);
                                }}
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

                    </div>

                    {/* Row A2: Maintenance Plant — scoped to the selected project's
                        Planning Plant (the dropdown refetches when the project's
                        Planning Plant changes; a user never sees plants from other
                        Planning Plants). Planning Plant + Description (PP) are
                        determined by the project and shown read-only. Maintenance
                        Plant lines up under Project Name, Planning Plant under
                        Project Code, Description (PP) spans the remaining width. */}
                    <div className="grid grid-cols-1 items-start gap-4 md:grid-cols-[minmax(0,1.4fr)_120px_minmax(0,1fr)]">
                      <MaintenancePlantField
                        control={form.control}
                        index={index}
                        planningPlantCode={
                          selectedProject?.planning_plant_code
                          ?? watchedTasks?.[index]?.planning_plant_code
                          ?? undefined
                        }
                        planningPlantDescription={
                          selectedProject?.planning_plant_description
                          ?? watchedTasks?.[index]?.planning_plant_description
                          ?? undefined
                        }
                      />
                    </div>

                    {/* Row B: Activity (25%) | Sub-Activity (75%) — own full-width row
                        so long sub-activity names show in full, uncramped. Selections
                        come from the Activity Master (Settings → Activity Master),
                        never hardcoded here. */}
                    <div className="grid grid-cols-[1fr_3fr] gap-4">
                      <FormField
                        control={form.control}
                        name={`tasks.${index}.activity_id`}
                        render={({ field: f }) => (
                          <FormItem className="min-w-0">
                            <FormLabel className="block text-xs leading-none text-muted-foreground">
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
                              <FormLabel className="block text-xs leading-none text-muted-foreground">
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

                    {/* Row B2: Tags / Docs / BOM / Spares. The sub-activity's
                        benchmarked count is starred/highlighted with its target;
                        the rest are optional operational counts. */}
                    <div className="grid gap-4 sm:grid-cols-4">
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
                                        ? "block text-xs font-medium leading-none text-foreground"
                                        : "block text-xs leading-none text-muted-foreground"
                                    }
                                  >
                                    {label}
                                    {isTarget && (
                                      <>
                                        <span className="text-destructive"> *</span>
                                        <span className="font-normal text-muted-foreground">
                                          {" "}(Target: {formatInt(sub!.benchmark_value)}/{sub!.benchmark_period_days ?? 1}d)
                                        </span>
                                      </>
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

                    {/* Row B3: Remarks — per-activity free text (own full-width row). */}
                    <FormField
                      control={form.control}
                      name={`tasks.${index}.description`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="block text-xs leading-none text-muted-foreground">
                            Remarks (optional)
                          </FormLabel>
                          <FormControl>
                            <Input placeholder="What did you work on?" {...f} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />

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
                </>
              )}
            </div>

            <Separator />

            {/* ── Remarks (general — primary note for leave-type days) ── */}
            <FormField
              control={form.control}
              name="remarks"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    Remarks{" "}
                    <span className="font-normal text-muted-foreground">(optional)</span>
                  </FormLabel>
                  <FormControl>
                    <Textarea
                      rows={3}
                      placeholder="Anything to note about this day?"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

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
              <Button type="submit" loading={isPending} disabled={!!existingReportForDate}>
                {mode === "create" ? "Save Draft" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
