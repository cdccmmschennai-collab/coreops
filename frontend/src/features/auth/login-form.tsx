"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Eye, EyeOff } from "lucide-react";

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

type LoginCandidate = { employee_code: string; name: string };

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/dashboard";
  const auth = useAuth();
  const [formError, setFormError] = React.useState<string | null>(null);
  const [showPassword, setShowPassword] = React.useState(false);
  // When a typed name matches several accounts the backend returns candidates
  // instead of failing; we show them so the user can pick the right account.
  const [candidates, setCandidates] = React.useState<LoginCandidate[] | null>(null);

  const form = useForm<LoginInput>({
    resolver: zodResolver(loginSchema),
    defaultValues: { identifier: "", password: "" },
  });

  // Already signed in → leave the login page.
  React.useEffect(() => {
    if (auth.status === "authenticated") router.replace(next);
  }, [auth.status, next, router]);

  const mutation = useMutation<TokenResponse, AppError, LoginInput>({
    mutationFn: (input) => authApi.login(input),
    onSuccess: async (data) => {
      setFormError(null);
      setCandidates(null);
      await auth.login(data.access_token);
      router.replace(next);
    },
    onError: (error) => {
      if (error instanceof AppError && error.code === "ambiguous_identifier") {
        const list = (error.details?.candidates as LoginCandidate[] | undefined) ?? [];
        setCandidates(list);
        setFormError(null);
        return;
      }
      setCandidates(null);
      if (error instanceof AppError && error.status === 429) {
        setFormError("Too many attempts. Please wait a few minutes and try again.");
      } else if (error instanceof AppError && error.status === 401) {
        setFormError("Invalid login or password.");
      } else {
        setFormError(error.message || "Something went wrong. Please try again.");
      }
    },
  });

  // Re-submit with the chosen account's employee code + the password already
  // entered (the field still holds it; no need to re-type).
  const selectCandidate = (candidate: LoginCandidate) => {
    setFormError(null);
    mutation.mutate({
      identifier: candidate.employee_code,
      password: form.getValues("password"),
    });
  };

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
          onSubmit={form.handleSubmit((values) => {
            setCandidates(null);
            mutation.mutate(values);
          })}
          noValidate
        >
          <FormField
            control={form.control}
            name="identifier"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Email</FormLabel>
                <FormControl>
                  <Input
                    type="text"
                    autoComplete="username"
                    placeholder="Enter your Email / Emp ID / Name"
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
                  <div className="relative">
                    <Input
                      type={showPassword ? "text" : "password"}
                      autoComplete="current-password"
                      placeholder="Enter your password"
                      className="pr-10"
                      {...field}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((s) => !s)}
                      className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? (
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
          <Button type="submit" size="lg" className="w-full" loading={mutation.isPending}>
            Sign in
          </Button>
        </form>
      </Form>

      {candidates && candidates.length > 0 && (
        <div className="mt-4 rounded-md border border-border bg-muted/40 p-3">
          <p className="mb-2 text-sm font-medium">
            Multiple accounts match that name. Select yours:
          </p>
          <ul className="space-y-2">
            {candidates.map((candidate) => (
              <li key={candidate.employee_code}>
                <Button
                  type="button"
                  variant="secondary"
                  className="flex w-full items-center justify-between"
                  disabled={mutation.isPending}
                  onClick={() => selectCandidate(candidate)}
                >
                  <span>{candidate.name}</span>
                  <span className="text-muted-foreground">{candidate.employee_code}</span>
                </Button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
