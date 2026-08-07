"use client";

import { useMemo } from "react";

import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";

import type { ProjectViewer } from "../permissions";
import type { Project } from "../types";

/**
 * Resolve the current user's authority over ONE project.
 *
 * The single place the client combines the role-level capability with the
 * project's Head row, so the Edit button, the /edit page guard and the Tag
 * Scope tab can never disagree about who is a project administrator.
 *
 * `project` is optional so callers can invoke the hook before their query has
 * resolved (hooks must not sit behind an early return). Until the project
 * loads, Head authority reads false — a PM is still a PM, and a Head simply
 * sees the restricted view for the moment before data arrives.
 */
export function useProjectAuthority(project: Project | undefined): ProjectViewer {
  const { role, employeeId } = useAuth();
  const canManage = can(role, "project.manage");
  const headEmployeeId = project?.head_employee_id ?? null;

  return useMemo(
    () => ({
      canManage,
      isHead: !!employeeId && !!headEmployeeId && employeeId === headEmployeeId,
    }),
    [canManage, employeeId, headEmployeeId],
  );
}
