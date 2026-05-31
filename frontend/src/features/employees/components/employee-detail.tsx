"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pencil, UserX } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { useUser } from "@/features/users/hooks";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { DeactivateDialog } from "./deactivate-dialog";
import { StatusBadge } from "./status-badge";
import { useEmployee } from "../hooks";
import type { Employee } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

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

  const [confirm, setConfirm] = React.useState<Employee | null>(null);

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
            <Row label="Status" value={<StatusBadge status={emp.status} />} />
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
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
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Account</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row
                label="Linked user"
                value={
                  !emp.user_id ? (
                    <Badge variant="neutral">No account</Badge>
                  ) : canManage && linkedUserQuery.data ? (
                    <span>{linkedUserQuery.data.email}</span>
                  ) : (
                    <Badge variant="info">Linked account</Badge>
                  )
                }
              />
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
