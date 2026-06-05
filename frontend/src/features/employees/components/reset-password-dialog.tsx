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
import { Input } from "@/components/ui/input";
import { AppError } from "@/lib/api-client";

import { useResetEmployeeAccountPassword } from "../hooks";

const schema = z.object({
  new_password: z.string().min(8, "Password must be at least 8 characters"),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  employeeId: string;
  employeeName: string;
  onCancel: () => void;
}

export function ResetPasswordForm({ employeeId, employeeName, onCancel }: Props) {
  const reset = useResetEmployeeAccountPassword(employeeId);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { new_password: "" },
  });

  async function onSubmit(values: FormValues) {
    try {
      await reset.mutateAsync(values);
      toast.success(`Password reset for ${employeeName}`);
      form.reset();
      onCancel();
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not reset password.");
    }
  }

  return (
    <Card className="mt-3 border-primary/20 bg-primary/[0.025]">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Reset password</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form className="space-y-3" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="new_password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">New password</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="Min. 8 characters" className="h-8 text-sm" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex gap-2 pt-1">
              <Button type="submit" size="sm" loading={reset.isPending}>
                Set password
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => { form.reset(); onCancel(); }}
                disabled={reset.isPending}
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
