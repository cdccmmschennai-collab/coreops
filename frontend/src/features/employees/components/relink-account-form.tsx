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
import { useUsers } from "@/features/users/hooks";
import { AppError } from "@/lib/api-client";

import { useRelinkEmployeeAccount } from "../hooks";

const schema = z.object({ user_id: z.string().min(1, "Select a user account") });
type FormValues = z.infer<typeof schema>;

interface Props {
  employeeId: string;
  employeeName: string;
  onCancel: () => void;
}

export function RelinkAccountForm({ employeeId, employeeName, onCancel }: Props) {
  const relink = useRelinkEmployeeAccount(employeeId);
  const usersQuery = useUsers();

  // Only users not already linked to an employee are valid relink targets.
  const unlinked = (usersQuery.data?.items ?? []).filter((u) => !u.linked_employee);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { user_id: "" },
  });

  async function onSubmit(values: FormValues) {
    try {
      await relink.mutateAsync(values);
      toast.success(`Account relinked for ${employeeName}`);
      onCancel();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not relink account.");
    }
  }

  return (
    <Card className="mt-3 border-primary/20 bg-primary/[0.025]">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Relink account</CardTitle>
      </CardHeader>
      <CardContent>
        {usersQuery.isLoading ? (
          <p className="py-2 text-sm text-muted-foreground">Loading accounts…</p>
        ) : unlinked.length === 0 ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              No unlinked user accounts are available. Create a new account or unlink
              one from another employee first.
            </p>
            <Button type="button" size="sm" variant="ghost" onClick={onCancel}>
              Close
            </Button>
          </div>
        ) : (
          <Form {...form}>
            <form className="space-y-3" onSubmit={form.handleSubmit(onSubmit)} noValidate>
              <FormField
                control={form.control}
                name="user_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-xs">Link to user account</FormLabel>
                    <Select value={field.value} onValueChange={field.onChange}>
                      <FormControl>
                        <SelectTrigger className="h-8 text-sm">
                          <SelectValue placeholder="Select an account" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {unlinked.map((u) => (
                          <SelectItem key={u.id} value={u.id}>
                            {u.email}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex gap-2 pt-1">
                <Button type="submit" size="sm" loading={relink.isPending}>
                  Relink account
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={onCancel}
                  disabled={relink.isPending}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </Form>
        )}
      </CardContent>
    </Card>
  );
}
