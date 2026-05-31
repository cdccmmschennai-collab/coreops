"use client";

import { SearchInput } from "@/components/data/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { EMPLOYEE_STATUSES, STATUS_LABEL } from "../schemas";
import type { EmployeeStatus } from "../types";

export interface EmployeeFilterValues {
  q: string;
  department: string;
  status: EmployeeStatus | "";
}

const ALL = "all";

export function EmployeesFilters({
  values,
  onChange,
}: {
  values: EmployeeFilterValues;
  onChange: (patch: Partial<EmployeeFilterValues>) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput
        className="sm:w-64"
        value={values.q}
        onChange={(q) => onChange({ q })}
        placeholder="Search name or code…"
      />
      <SearchInput
        className="sm:w-56"
        value={values.department}
        onChange={(department) => onChange({ department })}
        placeholder="Filter by department…"
      />
      <Select
        value={values.status === "" ? ALL : values.status}
        onValueChange={(v) => onChange({ status: v === ALL ? "" : (v as EmployeeStatus) })}
      >
        <SelectTrigger className="sm:w-44">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {EMPLOYEE_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {STATUS_LABEL[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
