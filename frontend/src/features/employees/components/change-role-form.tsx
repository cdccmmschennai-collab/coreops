"use client";

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { UserRole } from "@/features/users/types";
import { AppError } from "@/lib/api-client";

import { useChangeEmployeeAccountRole } from "../hooks";

const schema = z.object({ role: z.enum(["employee", "project_manager"]) });
type FormValues = z.infer<typeof schema>;

interface Props {
  employeeId: string;
  employeeName: string;
  // Accepts the full API role union; any non-PM/legacy value defaults to "employee".
  currentRole: UserRole;
  onCancel: () => void;
}

export function ChangeRoleForm({ employeeId, employeeName, currentRole, onCancel }: Props) {
  const changeRole = useChangeEmployeeAccountRole(employeeId);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      role: currentRole === "project_manager" ? "project_manager" : "employee",
    },
  });

  async function onSubmit(values: FormValues) {
    if (values.role === currentRole) {
      onCancel();
      return;
    }
    try {
      await changeRole.mutateAsync(values);
      toast.success(`Role updated for ${employeeName}`);
      onCancel();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not change role.");
    }
  }

  return (
    <Card className="mt-3 border-primary/20 bg-primary/[0.025]">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Change role</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form className="space-y-3" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Account role</FormLabel>
                  <Select value={field.value} onValueChange={field.onChange}>
                    <FormControl>
                      <SelectTrigger className="h-8 text-sm">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="employee">Employee</SelectItem>
                      <SelectItem value="project_manager">Project Manager</SelectItem>
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex gap-2 pt-1">
              <Button type="submit" size="sm" loading={changeRole.isPending}>
                Save role
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={onCancel}
                disabled={changeRole.isPending}
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
