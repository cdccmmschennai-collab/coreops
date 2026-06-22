"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Pencil, Trash2 } from "lucide-react";

import { ErrorState } from "@/components/feedback/error-state";
import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuth } from "@/features/auth/auth-provider";
import { AppError } from "@/lib/api-client";
import { can } from "@/lib/rbac";

import { DeleteDialog } from "./delete-dialog";
import { StatusBadge } from "./status-badge";
import { useEmployeeOptions } from "../employee-options";
import { useAttendance } from "../hooks";
import type { Attendance } from "../types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

export function AttendanceDetail({ id }: { id: string }) {
  const router = useRouter();
  const { role } = useAuth();
  const canManage = can(role, "attendance.manage");

  const query = useAttendance(id);
  const record = query.data;
  const { byId } = useEmployeeOptions();
  const [confirm, setConfirm] = React.useState<Attendance | null>(null);

  if (query.isLoading) {
    return (
      <>
        <Skeleton className="mb-6 h-10 w-64" />
        <Skeleton className="h-56 max-w-xl" />
      </>
    );
  }

  if (query.isError || !record) {
    const notFound = query.error instanceof AppError && query.error.status === 404;
    return (
      <ErrorState
        title={notFound ? "Record not found" : "Couldn't load record"}
        message={notFound ? "This attendance record may have been deleted." : "Please try again."}
        onRetry={notFound ? undefined : () => void query.refetch()}
      />
    );
  }

  const employeeName = byId.get(record.employee_id) ?? "Employee";

  return (
    <>
      <Link href="/attendance" className="text-sm text-primary hover:underline">
        ← Attendance
      </Link>
      <PageHeader
        className="mt-2"
        title={`${employeeName} · ${record.attendance_date}`}
        actions={
          canManage ? (
            <>
              <Button variant="secondary" asChild>
                <Link href={`/attendance/${record.id}/edit`}>
                  <Pencil className="h-4 w-4" />
                  Edit
                </Link>
              </Button>
              <Button variant="danger" onClick={() => setConfirm(record)}>
                <Trash2 className="h-4 w-4" />
                Delete
              </Button>
            </>
          ) : null
        }
      />

      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent className="divide-y divide-border">
          <Row label="Employee" value={employeeName} />
          <Row label="Date" value={record.attendance_date} />
          <Row label="Status" value={<StatusBadge status={record.status} />} />
        </CardContent>
      </Card>

      <DeleteDialog
        record={confirm}
        onOpenChange={(open) => {
          if (!open) setConfirm(null);
        }}
        onDone={() => router.push("/attendance")}
      />
    </>
  );
}
