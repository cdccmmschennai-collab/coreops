"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Plus } from "lucide-react";

import { PageHeader } from "@/components/shell/page-header";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/features/auth/auth-provider";
import { can } from "@/lib/rbac";

import { AttendanceFilters, type AttendanceFilterValues } from "./attendance-filters";
import { AttendanceTable } from "./attendance-table";
import { DeleteDialog } from "./delete-dialog";
import { useAttendanceList } from "../hooks";
import { ATTENDANCE_STATUSES } from "../schemas";
import type { Attendance, AttendanceListParams, AttendanceStatus } from "../types";

const LIMIT = 20;

function parseStatus(value: string | null): AttendanceStatus | "" {
  return value && (ATTENDANCE_STATUSES as readonly string[]).includes(value)
    ? (value as AttendanceStatus)
    : "";
}

export function AttendanceView() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const { role } = useAuth();
  const canManage = can(role, "attendance.manage");

  const params: AttendanceListParams = {
    employee_id: searchParams.get("employee_id") ?? "",
    status: parseStatus(searchParams.get("status")),
    from: searchParams.get("from") ?? "",
    to: searchParams.get("to") ?? "",
    limit: LIMIT,
    offset: Math.max(0, Number(searchParams.get("offset") ?? "0") || 0),
  };

  const query = useAttendanceList(params);
  const [deleteTarget, setDeleteTarget] = React.useState<Attendance | null>(null);

  function commit(next: URLSearchParams) {
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname);
  }

  function onFilterChange(patch: Partial<AttendanceFilterValues>) {
    const next = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    next.delete("offset");
    commit(next);
  }

  function onPageChange(offset: number) {
    const next = new URLSearchParams(searchParams.toString());
    if (offset > 0) next.set("offset", String(offset));
    else next.delete("offset");
    commit(next);
  }

  const addButton = canManage ? (
    <Button asChild>
      <Link href="/attendance/new">
        <Plus className="h-4 w-4" />
        Record attendance
      </Link>
    </Button>
  ) : null;

  const count = query.data?.total;

  return (
    <>
      <PageHeader
        title="Attendance"
        subtitle={
          count !== undefined ? `${count} ${count === 1 ? "record" : "records"}` : undefined
        }
        actions={addButton}
      />
      <div className="mb-4">
        <AttendanceFilters
          values={{
            employee_id: params.employee_id,
            status: params.status,
            from: params.from,
            to: params.to,
          }}
          onChange={onFilterChange}
        />
      </div>
      <AttendanceTable
        data={query.data}
        isLoading={query.isLoading}
        isError={query.isError}
        onRetry={() => void query.refetch()}
        onPageChange={onPageChange}
        canManage={canManage}
        onRequestDelete={setDeleteTarget}
        emptyAction={addButton}
      />
      <DeleteDialog
        record={deleteTarget}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
      />
    </>
  );
}
