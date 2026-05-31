"use client";

import { SearchInput } from "@/components/data/search-input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { PROJECT_STATUSES, PROJECT_STATUS_LABEL } from "../schemas";
import type { ProjectStatus } from "../types";

export interface ProjectFilterValues {
  q: string;
  status: ProjectStatus | "";
}

const ALL = "all";

export function ProjectsFilters({
  values,
  onChange,
}: {
  values: ProjectFilterValues;
  onChange: (patch: Partial<ProjectFilterValues>) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <SearchInput
        className="sm:w-72"
        value={values.q}
        onChange={(q) => onChange({ q })}
        placeholder="Search code, name or client…"
      />
      <Select
        value={values.status === "" ? ALL : values.status}
        onValueChange={(v) => onChange({ status: v === ALL ? "" : (v as ProjectStatus) })}
      >
        <SelectTrigger className="sm:w-44">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {PROJECT_STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {PROJECT_STATUS_LABEL[s]}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
