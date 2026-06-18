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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { AppError } from "@/lib/api-client";

import { useCreateEmployeeAccount } from "../hooks";

const schema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
  role: z.enum(["employee", "project_manager"]),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  employeeId: string;
  employeeName: string;
  onCancel: () => void;
}

export function CreateAccountForm({ employeeId, employeeName, onCancel }: Props) {
  const createAccount = useCreateEmployeeAccount(employeeId);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", password: "", role: "employee" },
  });

  async function onSubmit(values: FormValues) {
    try {
      await createAccount.mutateAsync(values);
      toast.success(`Account created for ${employeeName}`);
      form.reset();
      onCancel();
    } catch (err) {
      if (err instanceof AppError && err.status === 409 && /email/i.test(err.message)) {
        form.setError("email", { message: err.message });
      } else {
        toast.error(err instanceof AppError ? err.message : "Could not create account.");
      }
    }
  }

  return (
    <Card className="mt-3 border-primary/20 bg-primary/[0.025]">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">Create login account</CardTitle>
      </CardHeader>
      <CardContent>
        <Form {...form}>
          <form className="space-y-3" onSubmit={form.handleSubmit(onSubmit)} noValidate>
            <FormField
              control={form.control}
              name="email"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Email address</FormLabel>
                  <FormControl>
                    <Input type="email" placeholder="name@company.com" className="h-8 text-sm" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="role"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Role</FormLabel>
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

            <FormField
              control={form.control}
              name="password"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-xs">Temporary password</FormLabel>
                  <FormControl>
                    <Input type="password" placeholder="Min. 8 characters" className="h-8 text-sm" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="flex gap-2 pt-1">
              <Button type="submit" size="sm" loading={createAccount.isPending}>
                Create account
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => { form.reset(); onCancel(); }}
                disabled={createAccount.isPending}
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
