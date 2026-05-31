"use client";

import * as React from "react";

import { ErrorState } from "@/components/feedback/error-state";
import { useAuth } from "@/features/auth/auth-provider";
import { can, type Capability } from "@/lib/rbac";

/** Client-side capability guard. The API enforces this server-side regardless. */
export function RequireCapability({
  capability,
  children,
}: {
  capability: Capability;
  children: React.ReactNode;
}) {
  const { role } = useAuth();
  if (!can(role, capability)) {
    return (
      <ErrorState
        title="Not allowed"
        message="You don't have permission to view this page."
      />
    );
  }
  return <>{children}</>;
}
