"use client";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { useEmployeeOptions } from "../employee-options";
import { ATTENDANCE_STATUSES, ATTENDANCE_STATUS_LABEL } from "../schemas";
import type { AttendanceStatus } from "../types";

export interface AttendanceFilterValues {
  employee_id: string;
  status: AttendanceStatus | "";
  from: string;
  to: string;
}

const ALL = "all";

export function AttendanceFilters({
  values,
  onChange,
}: {
  values: AttendanceFilterValues;
  onChange: (patch: Partial<AttendanceFilterValues>) => void;
}) {
  const { items } = useEmployeeOptions();

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      <Select
        value={values.employee_id === "" ? ALL : values.employee_id}
        onValueChange={(v) => onChange({ employee_id: v === ALL ? "" : v })}
      >
        <SelectTrigger className="sm:w-56">
          <SelectValue placeholder="Employee" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All employees</SelectItem>
          {items.map((e) => (
            <SelectItem key={e.id} value={e.id}>
              {e.full_name} · {e.employee_code}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={values.status === "" ? ALL : values.status}
        onValueChange={(v) => onChange({ status: v === ALL ? "" : (v as AttendanceStatus) })}
      >
        <SelectTrigger className="sm:w-40">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {ATTENDANCE_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {ATTENDANCE_STATUS_LABEL[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <div className="flex items-center gap-1">
        <Input
          type="date"
          className="sm:w-40"
          value={values.from}
          onChange={(e) => onChange({ from: e.target.value })}
          aria-label="From date"
        />
        <span className="text-muted-foreground">→</span>
        <Input
          type="date"
          className="sm:w-40"
          value={values.to}
          onChange={(e) => onChange({ to: e.target.value })}
          aria-label="To date"
        />
      </div>
    </div>
  );
}
