"use client";

import { SearchInput } from "@/components/data/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import {
  TASK_PRIORITIES,
  TASK_PRIORITY_LABEL,
  TASK_STATUSES,
  TASK_STATUS_LABEL,
} from "../schemas";
import type { TaskPriority, TaskStatus } from "../types";

export interface TaskFilterValues {
  q: string;
  status: TaskStatus | "";
  priority: TaskPriority | "";
}

interface TasksFiltersProps {
  values: TaskFilterValues;
  onChange: (patch: Partial<TaskFilterValues>) => void;
}

export function TasksFilters({ values, onChange }: TasksFiltersProps) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
      <SearchInput
        value={values.q}
        onChange={(q) => onChange({ q })}
        placeholder="Search tasks…"
        className="sm:max-w-xs"
      />
      <Select
        value={values.status || "all"}
        onValueChange={(v) => onChange({ status: v === "all" ? "" : (v as TaskStatus) })}
      >
        <SelectTrigger className="w-full sm:w-40">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All statuses</SelectItem>
          {TASK_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {TASK_STATUS_LABEL[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={values.priority || "all"}
        onValueChange={(v) => onChange({ priority: v === "all" ? "" : (v as TaskPriority) })}
      >
        <SelectTrigger className="w-full sm:w-40">
          <SelectValue placeholder="Priority" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="all">All priorities</SelectItem>
          {TASK_PRIORITIES.map((p) => (
            <SelectItem key={p} value={p}>
              {TASK_PRIORITY_LABEL[p]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
