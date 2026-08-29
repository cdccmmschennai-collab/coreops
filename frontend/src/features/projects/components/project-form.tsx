"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
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
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Combobox } from "@/components/ui/combobox";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useMaintenancePlantOptions, usePlanningPlants } from "@/features/plant-master/hooks";
import { AppError } from "@/lib/api-client";

import { useCreateProject, useUpdateProject } from "../hooks";
import {
  PROJECT_STATUSES,
  PROJECT_STATUS_LABEL,
  projectFormSchema,
  toCreateBody,
  toUpdateBody,
  type ProjectFormValues,
} from "../schemas";

interface ProjectFormProps {
  mode: "create" | "edit";
  defaultValues: ProjectFormValues;
  projectId?: string;
}

export function ProjectForm({ mode, defaultValues, projectId }: ProjectFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);
  // Asked before Tag based is switched off on a project that is stored as
  // TAG_BASED. Turning it off changes how the project is reported on (no tag
  // cap, no scoped progress), so it should not happen on a stray click - but it
  // deletes nothing, so the dialog is a confirmation, not a destructive warning.
  // Only for `edit`: a project being created has no scope to switch off.
  const [confirmScopeOff, setConfirmScopeOff] = React.useState(false);
  const scopeWasTagBased = mode === "edit" && defaultValues.scope_type === "TAG_BASED";

  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues,
  });

  const createMutation = useCreateProject();
  const updateMutation = useUpdateProject(projectId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const { data: planningPlants } = usePlanningPlants();
  const planningPlantOptions = React.useMemo(
    () =>
      (planningPlants ?? []).map((pp) => ({
        value: pp.id,
        label: pp.code,
        sublabel: pp.description,
      })),
    [planningPlants],
  );
  const watchedPlanningPlantId = form.watch("planning_plant_id");
  const selectedPlanningPlant = watchedPlanningPlantId
    ? (planningPlants ?? []).find((pp) => pp.id === watchedPlanningPlantId)
    : undefined;

  // Maintenance Plant options scoped to the selected Planning Plant — refetched
  // whenever the Planning Plant code changes; disabled until one is chosen.
  const planningPlantCode = selectedPlanningPlant?.code;
  const { options: maintenancePlantOptions, isLoading: maintenancePlantsLoading } =
    useMaintenancePlantOptions(true, planningPlantCode, !!planningPlantCode);

  function handleError(error: unknown) {
    if (error instanceof AppError) {
      if (error.status === 409) {
        form.setError("code", { message: error.message });
      } else {
        setFormError(error.message);
      }
    } else {
      setFormError("Something went wrong. Please try again.");
    }
  }

  async function onSubmit(values: ProjectFormValues) {
    setFormError(null);
    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Project created" : "Changes saved");
      router.push(`/projects/${result.id}`);
    } catch (error) {
      handleError(error);
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
          <form className="space-y-4" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <div className="grid gap-4 sm:grid-cols-2">

              {/* Project Code — optional (migration 0078): left blank for a
                  project that has none yet (e.g. a Tag Estimation engagement),
                  in which case the employee enters one per activity on the
                  work report instead. Editable; uniqueness re-checked
                  server-side on change. */}
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project Code</FormLabel>
                    <FormControl>
                      <Input
                        {...field}
                        placeholder="e.g. GC19101900 (leave blank if not yet assigned)"
                      />
                    </FormControl>
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
                        {PROJECT_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {PROJECT_STATUS_LABEL[s]}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Project Title */}
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Project Title</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="Full project title" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Job Code — free text, entered by the PM */}
              <FormField
                control={form.control}
                name="job_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Job Code</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. J-615-2" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Project Name */}
              <FormField
                control={form.control}
                name="client"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project Name</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="Contractor / client name" />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Planning Plant + Maintenance Plant. A project belongs to one
                  Planning Plant (project master); the Maintenance Plant dropdown is
                  scoped to that Planning Plant's plants and reloads when it changes.
                  Description (PP) auto-derives from the Planning Plant, read-only. */}
              <div className="grid gap-4 sm:col-span-2 sm:grid-cols-3">
                <FormField
                  control={form.control}
                  name="planning_plant_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="block text-sm font-medium leading-none text-muted-foreground">
                        Planning Plant
                      </FormLabel>
                      <FormControl>
                        <Combobox
                          value={field.value || ""}
                          onValueChange={(v) => {
                            const changed = v !== field.value;
                            field.onChange(v);
                            // Maintenance Plants depend on the Planning Plant — clear
                            // any prior selection so a plant from the old PP can't linger.
                            if (changed) form.setValue("maintenance_plant_id", "");
                          }}
                          options={planningPlantOptions}
                          placeholder="Select planning plant…"
                          searchPlaceholder="Search planning plants…"
                          emptyMessage="No matching plants."
                          allowClear
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="space-y-2">
                  <label className="block text-sm font-medium leading-none text-muted-foreground">
                    Description (PP)
                  </label>
                  <Input
                    value={selectedPlanningPlant?.description ?? ""}
                    disabled
                    readOnly
                  />
                </div>
                <FormField
                  control={form.control}
                  name="maintenance_plant_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel className="block text-sm font-medium leading-none text-muted-foreground">
                        Maintenance Plant
                      </FormLabel>
                      <FormControl>
                        <Combobox
                          value={field.value || ""}
                          onValueChange={field.onChange}
                          options={maintenancePlantOptions}
                          placeholder={
                            planningPlantCode
                              ? maintenancePlantsLoading
                                ? "Loading plants…"
                                : "Select plant…"
                              : "Select a planning plant first"
                          }
                          searchPlaceholder="Search maintenance plants…"
                          emptyMessage="No plants for this Planning Plant."
                          disabled={!planningPlantCode}
                          allowClear
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              {/* Dates */}
              <FormField
                control={form.control}
                name="start_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Start date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {mode === "create" || !defaultValues.planned_completion_date ? (
                <FormField
                  control={form.control}
                  name="planned_completion_date"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Planned completion date</FormLabel>
                      <FormControl>
                        <Input type="date" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              ) : (
                <div className="flex flex-col gap-1.5">
                  <label className="text-sm font-medium leading-none">
                    Planned completion date
                  </label>
                  <Input
                    type="date"
                    value={defaultValues.planned_completion_date}
                    disabled
                    readOnly
                  />
                  <p className="text-xs text-muted-foreground">
                    Use the calendar icon on the project page to change this date (a reason is required).
                  </p>
                </div>
              )}
              <FormField
                control={form.control}
                name="actual_completion_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Actual completion date{" "}
                      <span className="font-normal text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Project Scope — classification only, no tag count asked for
                  here (that lives on the Tag Scope tab). A two-state setting, so
                  a switch rather than a dropdown: it reads at a glance and sits
                  in one grid cell beside the date above. */}
              <FormField
                control={form.control}
                name="scope_type"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel htmlFor="scope_type">Project Scope</FormLabel>
                    <div className="flex h-9 items-center justify-between gap-3 rounded-md border border-input bg-card px-3">
                      <span className="text-sm">Tag based</span>
                      <FormControl>
                        <Switch
                          id="scope_type"
                          checked={field.value === "TAG_BASED"}
                          onCheckedChange={(on) => {
                            // Turning it ON is unremarkable - it restores the
                            // project's preserved scope. Turning it OFF on a
                            // project that is stored as tag-based is confirmed
                            // first; the switch does not move until then.
                            if (!on && scopeWasTagBased) {
                              setConfirmScopeOff(true);
                              return;
                            }
                            field.onChange(on ? "TAG_BASED" : "NONE");
                          }}
                          aria-label="Tag based project"
                        />
                      </FormControl>
                    </div>
                    <FormMessage />

                    <AlertDialog open={confirmScopeOff} onOpenChange={setConfirmScopeOff}>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Disable Tag Scope?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This project will return to normal project reporting.
                            Existing tag-scope history will be preserved, but tag
                            limits and tag-based progress tracking will no longer
                            apply.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction
                            onClick={() => {
                              field.onChange("NONE");
                              setConfirmScopeOff(false);
                            }}
                          >
                            Disable Tag Scope
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </FormItem>
                )}
              />

              {/* Description */}
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem className="sm:col-span-2">
                    <FormLabel>Description <span className="text-muted-foreground font-normal">(optional)</span></FormLabel>
                    <FormControl>
                      <Textarea rows={3} placeholder="Additional notes about this project" {...field} />
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
                {mode === "create" ? "Create project" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
