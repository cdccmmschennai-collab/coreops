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
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useEmployeeOptions } from "@/features/attendance/employee-options";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";

import { useAssignableProjects, useCreateTask, useUpdateTask } from "../hooks";
import {
  EMPTY_TASK_FORM,
  TASK_PRIORITIES,
  TASK_PRIORITY_LABEL,
  taskFormSchema,
  toCreateBody,
  toUpdateBody,
  type TaskFormValues,
} from "../schemas";

interface TaskFormProps {
  mode: "create" | "edit";
  defaultValues?: TaskFormValues;
  taskId?: string;
}

export function TaskForm({ mode, defaultValues = EMPTY_TASK_FORM, taskId }: TaskFormProps) {
  const router = useRouter();
  const { role } = useAuth();
  const isPM = role === "project_manager";
  const [formError, setFormError] = React.useState<string | null>(null);
  const { items } = useEmployeeOptions();
  // Team leads assign within a project they lead; PMs assign to anyone.
  const { data: assignableProjects = [] } = useAssignableProjects({ enabled: !isPM });

  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema),
    defaultValues,
  });

  const projectId = form.watch("project_id");

  // With a single led project, pre-select it so the team lead only picks an assignee.
  React.useEffect(() => {
    if (!isPM && !projectId && assignableProjects.length === 1) {
      form.setValue("project_id", assignableProjects[0].project_id);
    }
  }, [isPM, projectId, assignableProjects, form]);

  const createMutation = useCreateTask();
  const updateMutation = useUpdateTask(taskId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  async function onSubmit(values: TaskFormValues) {
    setFormError(null);
    try {
      if (mode === "create") {
        const created = await createMutation.mutateAsync(toCreateBody(values));
        toast.success("Task created");
        router.push(`/tasks/${created.id}`);
      } else {
        await updateMutation.mutateAsync(toUpdateBody(values));
        toast.success("Task updated");
        router.push(`/tasks/${taskId}`);
      }
    } catch (err) {
      const message =
        err instanceof AppError ? err.message : "Something went wrong. Please try again.";
      setFormError(message);
    }
  }

  const selectedProject = assignableProjects.find((p) => p.project_id === projectId);
  const assigneeOptions: { id: string; name: string }[] = isPM
    ? items
        .filter((e) => e.status === "active")
        .map((e) => ({ id: e.id, name: e.full_name }))
    : (selectedProject?.members ?? []).map((m) => ({
        id: m.employee_id,
        name: m.name,
      }));
  const assigneeDisabled = !isPM && !selectedProject;

  return (
    <Card className="max-w-2xl">
      <CardContent className="pt-6">
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Title</FormLabel>
                  <FormControl>
                    <Input placeholder="e.g. Prepare Monthly Report" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="What needs to be done?"
                      rows={4}
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {!isPM && (
              <FormField
                control={form.control}
                name="project_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Project</FormLabel>
                    <Select
                      value={field.value}
                      onValueChange={(v) => {
                        field.onChange(v);
                        // Reset assignee when the project changes.
                        form.setValue("assigned_to_employee_id", "");
                      }}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select project" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {assignableProjects.length === 0 ? (
                          <div className="px-2 py-1.5 text-sm text-muted-foreground">
                            You don't lead any active projects
                          </div>
                        ) : (
                          assignableProjects.map((p) => (
                            <SelectItem key={p.project_id} value={p.project_id}>
                              {p.name} · {p.code}
                            </SelectItem>
                          ))
                        )}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
            )}

            <FormField
              control={form.control}
              name="assigned_to_employee_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Assign to</FormLabel>
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                    disabled={assigneeDisabled}
                  >
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue
                          placeholder={
                            assigneeDisabled ? "Select a project first" : "Select employee"
                          }
                        />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {assigneeOptions.length === 0 ? (
                        <div className="px-2 py-1.5 text-sm text-muted-foreground">
                          No assignable members
                        </div>
                      ) : (
                        assigneeOptions.map((e) => (
                          <SelectItem key={e.id} value={e.id}>
                            {e.name}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="priority"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Priority</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {TASK_PRIORITIES.map((p) => (
                          <SelectItem key={p} value={p}>
                            {TASK_PRIORITY_LABEL[p]}
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
                name="due_date"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Due date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {formError && (
              <p className="text-sm text-destructive" role="alert">
                {formError}
              </p>
            )}

            <div className="flex gap-2 pt-2">
              <Button type="submit" disabled={isPending}>
                {mode === "create" ? "Create task" : "Save changes"}
              </Button>
              <Button
                type="button"
                variant="secondary"
                onClick={() => router.back()}
                disabled={isPending}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
