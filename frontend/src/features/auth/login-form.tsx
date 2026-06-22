"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";

import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Brand } from "@/components/shell/brand";
import { authApi } from "@/features/auth/api";
import { useAuth } from "@/features/auth/auth-provider";
import { loginSchema, type LoginInput } from "@/features/auth/schemas";
import { AppError } from "@/lib/api-client";
import type { TokenResponse } from "@/types/api";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/dashboard";
  const auth = useAuth();
  const [formError, setFormError] = React.useState<string | null>(null);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });

  // Already signed in → leave the login page.
  React.useEffect(() => {
    if (auth.status === "authenticated") router.replace(next);
  }, [auth.status, next, router]);

  const mutation = useMutation<TokenResponse, AppError, LoginInput>({
    mutationFn: (input) => authApi.login(input),
    onSuccess: async (data) => {
      setFormError(null);
      await auth.login(data.access_token);
      router.replace(next);
    },
    onError: (error) => {
      if (error instanceof AppError && error.status === 429) {
        setFormError("Too many attempts. Please wait a few minutes and try again.");
      } else if (error instanceof AppError && error.status === 401) {
        setFormError("Invalid email or password.");
      } else {
        setFormError(error.message || "Something went wrong. Please try again.");
      }
    },
  });

  return (
    <div className="w-full max-w-sm">
      <div className="mb-8">
        <Brand logoHeight={36} />
        <h1 className="mt-6 font-serif text-2xl font-semibold tracking-tight">
          Sign in to your workspace
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Submit daily reports, track projects, and review your team.
        </p>
      </div>

      {formError && (
        <div
          role="alert"
          className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
        >
          {formError}
        </div>
      )}

      <Form {...form}>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
          noValidate
        >
          <FormField
            control={form.control}
            name="email"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Work email</FormLabel>
                <FormControl>
                  <Input
                    type="email"
                    autoComplete="email"
                    placeholder="you@company.com"
                    {...field}
                  />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="password"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Password</FormLabel>
                <FormControl>
                  <Input type="password" autoComplete="current-password" {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <Button type="submit" size="lg" className="w-full" loading={mutation.isPending}>
            Sign in
          </Button>
        </form>
      </Form>
    </div>
  );
}
