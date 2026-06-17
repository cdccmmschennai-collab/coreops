"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

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
import { Textarea } from "@/components/ui/textarea";
import { useMaintenancePlantOptions } from "@/features/plant-master/hooks";
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

  const form = useForm<ProjectFormValues>({
    resolver: zodResolver(projectFormSchema),
    defaultValues,
  });

  const createMutation = useCreateProject();
  const updateMutation = useUpdateProject(projectId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  const { options: maintenancePlantOptions, byId: maintenancePlantById } = useMaintenancePlantOptions();
  const watchedMaintenancePlantId = form.watch("maintenance_plant_id");
  const selectedMaintenancePlant = watchedMaintenancePlantId
    ? maintenancePlantById.get(watchedMaintenancePlantId)
    : undefined;

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

              {/* Project Code — editable; uniqueness re-checked server-side on change */}
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project Code</FormLabel>
                    <FormControl>
                      <Input {...field} placeholder="e.g. GC19101900" />
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

              {/* Maintenance Plant — pick directly (searchable, ~100 options);
                  Planning Plant code/description auto-derive, read-only. */}
              <div className="grid gap-4 sm:col-span-2 sm:grid-cols-3">
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
                          placeholder="Select plant…"
                          searchPlaceholder="Search maintenance plants…"
                          emptyMessage="No matching plants."
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <div className="space-y-2">
                  <label className="block text-sm font-medium leading-none text-muted-foreground">
                    Planning Plant
                  </label>
                  <Input value={selectedMaintenancePlant?.planning_plant_code ?? ""} disabled readOnly />
                </div>
                <div className="space-y-2">
                  <label className="block text-sm font-medium leading-none text-muted-foreground">
                    Description (PP)
                  </label>
                  <Input
                    value={selectedMaintenancePlant?.planning_plant_description ?? ""}
                    disabled
                    readOnly
                  />
                </div>
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
