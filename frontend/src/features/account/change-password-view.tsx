"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { z } from "zod";

import { BackButton } from "@/components/shell/back-button";
import { PageHeader } from "@/components/shell/page-header";
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
import { authApi } from "@/features/auth/api";
import { AppError } from "@/lib/api-client";

const schema = z
  .object({
    current_password: z.string().min(1, "Enter your current password"),
    new_password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_new_password: z.string().min(1, "Confirm your new password"),
  })
  .refine((d) => d.new_password === d.confirm_new_password, {
    message: "Passwords do not match",
    path: ["confirm_new_password"],
  })
  .refine((d) => d.new_password !== d.current_password, {
    message: "New password must be different from the current password",
    path: ["new_password"],
  });

type FormValues = z.infer<typeof schema>;

export function ChangePasswordView() {
  const router = useRouter();
  const [showCurrent, setShowCurrent] = React.useState(false);
  const [showNew, setShowNew] = React.useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      current_password: "",
      new_password: "",
      confirm_new_password: "",
    },
  });

  const mutation = useMutation({
    mutationFn: (values: FormValues) =>
      authApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
      }),
  });

  async function onSubmit(values: FormValues) {
    try {
      await mutation.mutateAsync(values);
      // Current session is intentionally kept active — no re-login required.
      toast.success("Password updated");
      form.reset();
      router.push("/account");
    } catch (err) {
      if (err instanceof AppError && err.code === "invalid_credentials") {
        form.setError("current_password", { message: err.message });
        return;
      }
      if (err instanceof AppError && err.code === "validation_error") {
        form.setError("new_password", { message: err.message });
        return;
      }
      toast.error(
        err instanceof AppError ? err.message : "Could not update password.",
      );
    }
  }

  return (
    <>
      <BackButton href="/account" />
      <PageHeader
        title="Change Password"
        subtitle="Update the password you use to sign in to CoreOps."
      />

      <div className="max-w-md">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Update password</CardTitle>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <form
                className="space-y-4"
                onSubmit={form.handleSubmit(onSubmit)}
                noValidate
              >
                <FormField
                  control={form.control}
                  name="current_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Current Password</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type={showCurrent ? "text" : "password"}
                            autoComplete="current-password"
                            placeholder="Your current password"
                            className="pr-10"
                            {...field}
                          />
                          <button
                            type="button"
                            onClick={() => setShowCurrent((s) => !s)}
                            className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                            aria-label={showCurrent ? "Hide password" : "Show password"}
                          >
                            {showCurrent ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="new_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>New Password</FormLabel>
                      <FormControl>
                        <div className="relative">
                          <Input
                            type={showNew ? "text" : "password"}
                            autoComplete="new-password"
                            placeholder="Min. 8 characters"
                            className="pr-10"
                            {...field}
                          />
                          <button
                            type="button"
                            onClick={() => setShowNew((s) => !s)}
                            className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                            aria-label={showNew ? "Hide password" : "Show password"}
                          >
                            {showNew ? (
                              <EyeOff className="h-4 w-4" />
                            ) : (
                              <Eye className="h-4 w-4" />
                            )}
                          </button>
                        </div>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="confirm_new_password"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Confirm New Password</FormLabel>
                      <FormControl>
                        <Input
                          type="password"
                          autoComplete="new-password"
                          placeholder="Re-enter new password"
                          {...field}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="flex gap-2 pt-1">
                  <Button type="submit" loading={mutation.isPending}>
                    Update password
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    asChild
                    disabled={mutation.isPending}
                  >
                    <Link href="/account">Cancel</Link>
                  </Button>
                </div>
              </form>
            </Form>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
