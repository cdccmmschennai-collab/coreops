"use client";

import { useAuth } from "@/features/auth/auth-provider";
import { isManagerial } from "@/lib/rbac";

import { EmployeeDashboard } from "./employee-dashboard";
import { ProjectManagerDashboard } from "./project-manager-dashboard";

/**
 * Role-based dashboard switch. Project managers get a review-focused home
 * (approval queue, team submissions, team overview); everyone else gets the
 * employee dashboard (own reports, hours logged, quick actions).
 */
export function DashboardView() {
  const { role } = useAuth();
  return isManagerial(role) ? <ProjectManagerDashboard /> : <EmployeeDashboard />;
}
