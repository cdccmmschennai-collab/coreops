"use client";

import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useEmployeeOptions } from "@/features/attendance/employee-options";

import { useProjectOptions } from "../project-options";
import { WORK_REPORT_STATUSES, WORK_REPORT_STATUS_LABEL } from "../schemas";
import type { WorkReportStatus } from "../types";

export interface WorkReportFilterValues {
  employee_id: string;
  project_id: string;
  status: WorkReportStatus | "";
  from: string;
  to: string;
}

const ALL = "all";

export function WorkReportsFilters({
  values,
  showEmployee,
  onChange,
}: {
  values: WorkReportFilterValues;
  showEmployee: boolean;
  onChange: (patch: Partial<WorkReportFilterValues>) => void;
}) {
  const { items: employees } = useEmployeeOptions();
  const { items: projects } = useProjectOptions();

  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
      {showEmployee && (
        <Select
          value={values.employee_id === "" ? ALL : values.employee_id}
          onValueChange={(v) => onChange({ employee_id: v === ALL ? "" : v })}
        >
          <SelectTrigger className="sm:w-56">
            <SelectValue placeholder="Employee" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>All employees</SelectItem>
            {employees.map((e) => (
              <SelectItem key={e.id} value={e.id}>
                {e.full_name} · {e.employee_code}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      <Select
        value={values.project_id === "" ? ALL : values.project_id}
        onValueChange={(v) => onChange({ project_id: v === ALL ? "" : v })}
      >
        <SelectTrigger className="sm:w-56">
          <SelectValue placeholder="Project" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All projects</SelectItem>
          {projects.map((p) => (
            <SelectItem key={p.id} value={p.id}>
              {p.name} · {p.code}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={values.status === "" ? ALL : values.status}
        onValueChange={(v) => onChange({ status: v === ALL ? "" : (v as WorkReportStatus) })}
      >
        <SelectTrigger className="sm:w-40">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {WORK_REPORT_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {WORK_REPORT_STATUS_LABEL[s]}
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
