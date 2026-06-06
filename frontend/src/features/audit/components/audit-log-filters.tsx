"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { ACTION_OPTIONS, ENTITY_OPTIONS, STATUS_OPTIONS, actionLabel } from "../schemas";

export interface AuditFilterValues {
  action: string;
  status: string;
  entity_type: string;
}

const ALL = "all";

export function AuditLogFilters({
  values,
  onChange,
}: {
  values: AuditFilterValues;
  onChange: (patch: Partial<AuditFilterValues>) => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Select
        value={values.action === "" ? ALL : values.action}
        onValueChange={(v) => onChange({ action: v === ALL ? "" : v })}
      >
        <SelectTrigger className="sm:w-56">
          <SelectValue placeholder="Action" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All actions</SelectItem>
          {ACTION_OPTIONS.map((a) => (
            <SelectItem key={a} value={a}>
              {actionLabel(a)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={values.entity_type === "" ? ALL : values.entity_type}
        onValueChange={(v) => onChange({ entity_type: v === ALL ? "" : v })}
      >
        <SelectTrigger className="sm:w-44">
          <SelectValue placeholder="Entity" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All entities</SelectItem>
          {ENTITY_OPTIONS.map((e) => (
            <SelectItem key={e} value={e}>
              {e}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select
        value={values.status === "" ? ALL : values.status}
        onValueChange={(v) => onChange({ status: v === ALL ? "" : v })}
      >
        <SelectTrigger className="sm:w-40">
          <SelectValue placeholder="Status" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {STATUS_OPTIONS.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
