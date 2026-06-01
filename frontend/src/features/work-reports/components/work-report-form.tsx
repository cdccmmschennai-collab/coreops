"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { AppError } from "@/lib/api-client";
import { formatMinutes } from "@/lib/format";

import { useCreateWorkReport, useUpdateWorkReport } from "../hooks";
import { useProjectOptions } from "../project-options";
import {
  DAY_STATUS_LABEL,
  DAY_STATUSES,
  EMPTY_TASK_ROW,
  WORK_LOCATION_LABEL,
  WORK_LOCATIONS,
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

const ALL_NONE = "__none__";

export function WorkReportForm({ mode, defaultValues, reportId }: WorkReportFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  const { items: projects } = useProjectOptions();

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
  const totalMinutes = (watchedTasks ?? []).reduce((sum, t) => {
    const n = Number(t?.minutes_spent);
    return sum + (Number.isFinite(n) && n > 0 ? n : 0);
  }, 0);

  const tasksError = form.formState.errors.tasks?.message;

  async function onSubmit(values: WorkReportFormValues) {
    setFormError(null);
    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Draft report created" : "Changes saved");
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

            {/* ── Row 1: Date, Day Status, Location ── */}
            <div className="grid gap-4 sm:grid-cols-3">
              <FormField
                control={form.control}
                name="report_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Date</FormLabel>
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
                    <FormLabel>Day Status</FormLabel>
                    <Select
                      value={field.value ?? ALL_NONE}
                      onValueChange={(v) => field.onChange(v === ALL_NONE ? undefined : v)}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select status" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={ALL_NONE}>— Not specified —</SelectItem>
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
                    <FormLabel>Office Location</FormLabel>
                    <Select
                      value={field.value ?? ALL_NONE}
                      onValueChange={(v) => field.onChange(v === ALL_NONE ? undefined : v)}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select location" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={ALL_NONE}>— Not specified —</SelectItem>
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

            {/* ── Row 2: Well Head, PM Plant ── */}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="well_head_no"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Well Head No. <span className="text-muted-foreground font-normal">(optional)</span></FormLabel>
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
                    <FormLabel>PM Plant <span className="text-muted-foreground font-normal">(optional)</span></FormLabel>
                    <FormControl>
                      <Input placeholder="PM plant identifier" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* ── Row 3: Maintenance Counters ── */}
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

            {/* ── Project Tasks ── */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-medium">Project activities</h3>
                {totalMinutes > 0 && (
                  <span className="text-sm text-muted-foreground">
                    Total: <span className="tabular font-medium">{formatMinutes(totalMinutes)}</span>
                  </span>
                )}
              </div>

              {fields.map((field, index) => (
                <div
                  key={field.id}
                  className="space-y-2 rounded-lg border border-border p-3"
                >
                  {/* Row A: Project | Description | Minutes | Remove */}
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)_7rem_auto] sm:items-start">
                    <FormField
                      control={form.control}
                      name={`tasks.${index}.project_id`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="sr-only">Project</FormLabel>
                          <Select value={f.value} onValueChange={f.onChange}>
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder="Project" />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {projects.map((p) => (
                                <SelectItem key={p.id} value={p.id}>
                                  {p.code} — {p.name}
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
                      name={`tasks.${index}.description`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="sr-only">Description</FormLabel>
                          <FormControl>
                            <Input placeholder="What did you work on?" {...f} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name={`tasks.${index}.minutes_spent`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="sr-only">Minutes (opt.)</FormLabel>
                          <FormControl>
                            <Input type="number" min={0} max={1440} placeholder="Min (opt.)" {...f} />
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

                  {/* Row B: Activity Type | Tags | Docs | BOM | Spares */}
                  <div className="grid gap-2 sm:grid-cols-[minmax(0,2fr)_repeat(4,5rem)]">
                    <FormField
                      control={form.control}
                      name={`tasks.${index}.activity_type`}
                      render={({ field: f }) => (
                        <FormItem>
                          <FormLabel className="text-xs text-muted-foreground">Activity type</FormLabel>
                          <FormControl>
                            <Input placeholder="e.g. Inspection, Testing…" {...f} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
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
                            <FormLabel className="text-xs text-muted-foreground">{label}</FormLabel>
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
              ))}

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

            {/* ── Remarks & Query ── */}
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="remarks"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Day Remarks <span className="text-muted-foreground font-normal">(optional)</span></FormLabel>
                    <FormControl>
                      <Textarea rows={3} placeholder="What did you accomplish today?" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="query_text"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Query / Issues <span className="text-muted-foreground font-normal">(optional)</span></FormLabel>
                    <FormControl>
                      <Textarea rows={3} placeholder="Any blockers or questions?" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

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
                {mode === "create" ? "Create draft" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
