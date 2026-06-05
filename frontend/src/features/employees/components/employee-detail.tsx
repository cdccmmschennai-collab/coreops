"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pencil, UserX } from "lucide-react";
import { toast } from "sonner";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { useOffices } from "@/features/offices/hooks";
import { useUser } from "@/features/users/hooks";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { CreateAccountForm } from "./create-account-dialog";
import { DeactivateDialog } from "./deactivate-dialog";
import { ResetPasswordForm } from "./reset-password-dialog";
import { StatusBadge } from "./status-badge";
import {
  useEmployee,
  useEmployeeTeam,
  useUpdateEmployeeAccountStatus,
} from "../hooks";
import type { Employee } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

const ROLE_LABEL: Record<string, string> = {
  project_manager: "Project Manager",
  employee: "Employee",
};

type AccountPanel = "none" | "create" | "reset_password";

export function EmployeeDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role } = useAuth();
  const canManage = can(role, "employee.manage");

  const query = useEmployee(id);
  const emp = query.data;

  const managerQuery = useEmployee(emp?.manager_id ?? undefined, {
    enabled: Boolean(emp?.manager_id),
  });
  const linkedUserQuery = useUser(emp?.user_id, canManage && Boolean(emp?.user_id));
  const teamQuery = useEmployeeTeam(canManage ? id : undefined);
  const officesQuery = useOffices(Boolean(emp?.office_id));
  const officeName = emp?.office_id
    ? (officesQuery.data?.items.find((o) => o.id === emp.office_id)?.name ?? emp.office_id)
    : null;

  const toggleStatus = useUpdateEmployeeAccountStatus(id);

  const [confirm, setConfirm] = React.useState<Employee | null>(null);
  const [accountPanel, setAccountPanel] = React.useState<AccountPanel>("none");

  const linkedUser = linkedUserQuery.data ?? null;

  async function handleToggleAccountStatus() {
    if (!linkedUser) return;
    const next = !linkedUser.is_active;
    try {
      await toggleStatus.mutateAsync({ is_active: next });
      toast.success(next ? "Account enabled" : "Account disabled");
    } catch (err) {
      toast.error(err instanceof AppError ? err.message : "Could not update account status.");
    }
  }

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-48" />
          <Skeleton className="h-48" />
        </div>
      </>
    );
  }

  if (query.isError || !emp) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Employee not found" : "Couldn't load employee"}
        message={notFound ? "This employee may have been deactivated." : "Please try again."}
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const subtitleParts = [emp.employee_code, emp.designation, emp.department].filter(
    Boolean,
  ) as string[];

  const directReportCount = teamQuery.data?.length ?? 0;

  return (
    <>
      <Link href="/employees" className="text-sm text-primary hover:underline">
        ← Employees
      </Link>
      <PageHeader
        className="mt-2"
        title={emp.full_name}
        subtitle={subtitleParts.join(" · ")}
        actions={
          canManage ? (
            <>
              <Button variant="secondary" asChild>
                <Link href={`/employees/${emp.id}/edit`}>
                  <Pencil className="h-4 w-4" />
                  Edit
                </Link>
              </Button>
              <Button variant="danger" onClick={() => setConfirm(emp)}>
                <UserX className="h-4 w-4" />
                Deactivate
              </Button>
            </>
          ) : null
        }
      />

      <div className="grid gap-4 md:grid-cols-2">
        {/* Profile card */}
        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
          </CardHeader>
          <CardContent className="divide-y divide-border">
            <Row label="Work email" value={emp.work_email ?? "—"} />
            <Row label="Phone" value={emp.phone ?? "—"} />
            <Row label="Department" value={emp.department ?? "—"} />
            <Row label="Designation" value={emp.designation ?? "—"} />
            <Row label="Join date" value={emp.date_of_joining ?? "—"} />
            <Row label="Office" value={officeName ?? "—"} />
            <Row label="Status" value={<StatusBadge status={emp.status} />} />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          {/* Reporting line card */}
          <Card>
            <CardHeader>
              <CardTitle>Reporting line</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row
                label="Manager"
                value={
                  !emp.manager_id ? (
                    "No manager"
                  ) : managerQuery.isLoading ? (
                    <Skeleton className="h-4 w-24" />
                  ) : managerQuery.data ? (
                    <Link
                      href={`/employees/${managerQuery.data.id}`}
                      className="text-primary hover:underline"
                    >
                      {managerQuery.data.full_name}
                    </Link>
                  ) : (
                    <span className="font-mono text-xs">{emp.manager_id}</span>
                  )
                }
              />
              {canManage && (
                <Row
                  label="Direct reports"
                  value={
                    teamQuery.isLoading ? (
                      <Skeleton className="h-4 w-16" />
                    ) : directReportCount === 0 ? (
                      "None"
                    ) : (
                      <Link
                        href={`/employees?manager_id=${emp.id}`}
                        className="text-primary hover:underline"
                      >
                        {directReportCount}{" "}
                        {directReportCount === 1 ? "employee" : "employees"}
                      </Link>
                    )
                  }
                />
              )}
            </CardContent>
          </Card>

          {/* Login account card */}
          <Card>
            <CardHeader>
              <CardTitle>Login account</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              {!emp.user_id ? (
                <>
                  <Row
                    label="Linked user"
                    value={<Badge variant="neutral">No account</Badge>}
                  />
                  {canManage && accountPanel === "none" && (
                    <div className="pt-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setAccountPanel("create")}
                      >
                        Create account
                      </Button>
                    </div>
                  )}
                  {canManage && accountPanel === "create" && (
                    <CreateAccountForm
                      employeeId={emp.id}
                      employeeName={emp.full_name}
                      onCancel={() => setAccountPanel("none")}
                    />
                  )}
                </>
              ) : linkedUserQuery.isLoading ? (
                <div className="space-y-2 py-2">
                  <Skeleton className="h-4 w-48" />
                  <Skeleton className="h-4 w-32" />
                  <Skeleton className="h-4 w-24" />
                </div>
              ) : linkedUser ? (
                <>
                  <Row label="Email" value={linkedUser.email} />
                  <Row
                    label="Role"
                    value={ROLE_LABEL[linkedUser.role] ?? linkedUser.role}
                  />
                  <Row
                    label="Account status"
                    value={
                      linkedUser.is_active ? (
                        <Badge variant="success">Active</Badge>
                      ) : (
                        <Badge variant="neutral">Disabled</Badge>
                      )
                    }
                  />
                  {linkedUser.last_login_at && (
                    <Row
                      label="Last login"
                      value={new Date(linkedUser.last_login_at).toLocaleString()}
                    />
                  )}
                  {canManage && accountPanel === "none" && (
                    <div className="flex flex-wrap gap-2 pt-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => setAccountPanel("reset_password")}
                      >
                        Reset password
                      </Button>
                      <Button
                        size="sm"
                        variant={linkedUser.is_active ? "danger" : "secondary"}
                        loading={toggleStatus.isPending}
                        onClick={() => void handleToggleAccountStatus()}
                      >
                        {linkedUser.is_active ? "Disable account" : "Enable account"}
                      </Button>
                    </div>
                  )}
                  {canManage && accountPanel === "reset_password" && (
                    <ResetPasswordForm
                      employeeId={emp.id}
                      employeeName={emp.full_name}
                      onCancel={() => setAccountPanel("none")}
                    />
                  )}
                </>
              ) : (
                <Row
                  label="Linked user"
                  value={<Badge variant="neutral">Account unavailable</Badge>}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      <DeactivateDialog
        employee={confirm}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        onDone={() => router.push("/employees")}
      />
    </>
  );
}
