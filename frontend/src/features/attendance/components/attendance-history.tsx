"use client";

import * as React from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";

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

/** History tab: the URL-driven, role-scoped attendance list (filters + table). */
export function AttendanceHistory() {
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

  return (
    <>
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
