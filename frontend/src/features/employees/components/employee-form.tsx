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
import { useUsers } from "@/features/users/hooks";
import { AppError } from "@/lib/api-client";

import { useCreateEmployee, useEmployees, useUpdateEmployee } from "../hooks";
import {
  EMPLOYEE_STATUSES,
  STATUS_LABEL,
  employeeFormSchema,
  toCreateBody,
  toUpdateBody,
  type EmployeeFormValues,
} from "../schemas";

const NONE = "none";

interface EmployeeFormProps {
  mode: "create" | "edit";
  defaultValues: EmployeeFormValues;
  employeeId?: string;
}

export function EmployeeForm({ mode, defaultValues, employeeId }: EmployeeFormProps) {
  const router = useRouter();
  const [formError, setFormError] = React.useState<string | null>(null);

  const form = useForm<EmployeeFormValues>({
    resolver: zodResolver(employeeFormSchema),
    defaultValues,
  });

  const createMutation = useCreateEmployee();
  const updateMutation = useUpdateEmployee(employeeId ?? "");
  const isPending = createMutation.isPending || updateMutation.isPending;

  // Manager options (exclude self when editing).
  const managersQuery = useEmployees({
    q: "",
    status: "",
    department: "",
    manager_id: "",
    limit: 100,
    offset: 0,
  });
  const managerOptions = (managersQuery.data?.items ?? []).filter(
    (e) => e.id !== employeeId,
  );

  // User-account options (create mode only — admin).
  const usersQuery = useUsers(mode === "create");
  const userOptions = usersQuery.data?.items ?? [];

  function handleError(error: unknown) {
    if (error instanceof AppError) {
      if (error.status === 409 && /code/i.test(error.message)) {
        form.setError("employee_code", { message: error.message });
      } else if (error.status === 409 && /email/i.test(error.message)) {
        form.setError("work_email", { message: error.message });
      } else {
        setFormError(error.message);
      }
    } else {
      setFormError("Something went wrong. Please try again.");
    }
  }

  async function onSubmit(values: EmployeeFormValues) {
    setFormError(null);
    try {
      const result =
        mode === "create"
          ? await createMutation.mutateAsync(toCreateBody(values))
          : await updateMutation.mutateAsync(toUpdateBody(values));
      toast.success(mode === "create" ? "Employee created" : "Changes saved");
      router.push(`/employees/${result.id}`);
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
              <FormField
                control={form.control}
                name="employee_code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Employee number</FormLabel>
                    <FormControl>
                      <Input {...field} disabled={mode === "edit"} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
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
                        {EMPLOYEE_STATUSES.map((s) => (
                          <SelectItem key={s} value={s}>
                            {STATUS_LABEL[s]}
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
                name="first_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>First name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="last_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Last name</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="work_email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Work email</FormLabel>
                    <FormControl>
                      <Input type="email" placeholder="name@company.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Phone</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="department"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Department</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="designation"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Designation</FormLabel>
                    <FormControl>
                      <Input {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="date_of_joining"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Join date</FormLabel>
                    <FormControl>
                      <Input type="date" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="manager_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Manager</FormLabel>
                    <Select
                      value={field.value === "" ? NONE : field.value}
                      onValueChange={(v) => field.onChange(v === NONE ? "" : v)}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="No manager" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value={NONE}>No manager</SelectItem>
                        {managerOptions.map((m) => (
                          <SelectItem key={m.id} value={m.id}>
                            {m.full_name} · {m.employee_code}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />
              {mode === "create" && (
                <FormField
                  control={form.control}
                  name="user_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Linked user account</FormLabel>
                      <Select
                        value={field.value === "" ? NONE : field.value}
                        onValueChange={(v) => field.onChange(v === NONE ? "" : v)}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="No account" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value={NONE}>No account</SelectItem>
                          {userOptions.map((u) => (
                            <SelectItem key={u.id} value={u.id}>
                              {u.email} · {u.role}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
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
                {mode === "create" ? "Create employee" : "Save changes"}
              </Button>
            </div>
          </form>
        </Form>
      </CardContent>
    </Card>
  );
}
